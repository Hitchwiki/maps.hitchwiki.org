"""Build the `road_island` polygon table from OpenStreetMap.

A "road island" is the patch of land enclosed by a ring of roads — the grass/asphalt
between the slip-roads of a junction, where hitchhikers actually stand. People drop pins
all around such a patch, so `show.py` merges every spot inside one road-island polygon
into a single spot.

For each cluster of nearby spots we fetch the surrounding road network from Overpass,
clip it to a disk around the cluster, union it with the disk's edge, and `polygonize` the
result: every enclosed face of the road network becomes a road-island polygon (WKT).

Mirrors hitchmap's `fetch-roads.py`. A slow, resumable one-off — run manually (not via
cron; see the README), only when you want to refresh the polygons: throttled Overpass
calls, incremental commits, and a checkpoint so an interrupted run resumes.
Re-running de-dupes against existing rows (by WKT) so nothing is lost or duplicated.
"""

import logging
import math
import time

from shapely.geometry import LineString, Point
from shapely.ops import polygonize, unary_union

from hitch.extensions import db
from hitch.models import RoadIsland
from hitch.scripts.map_revision import mark_map_data_dirty
from hitch.scripts.osm_areas_common import (
    clear_checkpoint,
    load_spot_coords,
    query_overpass,
    resume_clusters,
    save_progress,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

NAME = "sync_road_islands"
COMMIT_EVERY = 25  # clusters between DB commits + checkpoint saves

M_PER_DEG = 111_000  # rough metres per degree of latitude; good enough at road-island scale
ROAD_FILTER = "motorway|trunk|primary|secondary|tertiary|unclassified|residential|service"
MARGIN_M = 150  # pad the search disk beyond the cluster bbox so enclosing roads are included
MIN_RADIUS_M = 250
MAX_RADIUS_M = 2000


def _search_radius_m(cluster):
    """Disk radius (m) covering a cluster's bounding box plus a margin, clamped.

    `cluster` is a list of [lat, lon] pairs (from the snapshot).
    """
    lats = [p[0] for p in cluster]
    lons = [p[1] for p in cluster]
    mean_lat = sum(lats) / len(lats)
    lat_span = (max(lats) - min(lats)) * M_PER_DEG
    lon_span = (max(lons) - min(lons)) * M_PER_DEG * math.cos(math.radians(mean_lat))
    radius = math.hypot(lat_span, lon_span) / 2 + MARGIN_M
    return max(MIN_RADIUS_M, min(MAX_RADIUS_M, radius))


def _road_islands_for_cluster(cluster):
    """Return shapely polygons for the road-enclosed faces around one spot cluster."""
    lats = [p[0] for p in cluster]
    lons = [p[1] for p in cluster]
    center_lat = sum(lats) / len(lats)
    center_lon = sum(lons) / len(lons)
    radius_m = _search_radius_m(cluster)

    query = f"""
[out:json][timeout:120];
way(around:{radius_m:.0f},{center_lat},{center_lon})["highway"~"{ROAD_FILTER}"];
out geom;
"""
    lines = [
        LineString([(pt["lon"], pt["lat"]) for pt in el.get("geometry", [])])
        for el in query_overpass(query)
        if el.get("type") == "way" and len(el.get("geometry", [])) >= 2
    ]
    if not lines:
        return []

    # Work in degrees (EPSG:4326) — fine at this scale. Clip roads to a disk around the
    # cluster, then union them with the disk edge so the enclosing perimeter closes off
    # faces that the roads alone wouldn't (matching hitchmap's approach).
    radius_deg = radius_m / M_PER_DEG
    disk = Point(center_lon, center_lat).buffer(radius_deg)
    disk_area = disk.area

    clipped = [line.intersection(disk) for line in lines]
    network = unary_union([disk.exterior] + [g for g in clipped if not g.is_empty])

    islands = []
    for face in polygonize(network):
        # Drop slivers and the degenerate "whole disk" face (a cluster with no roads
        # crossing it) — neither is a real road island worth merging spots into.
        if face.area <= 0 or face.area >= 0.8 * disk_area:
            continue
        islands.append(face)
    return islands


def main():
    logger.info("SYNC ROAD ISLANDS SCRIPT STARTED")
    coords = load_spot_coords()
    clusters, start = resume_clusters(NAME, coords)

    # De-dupe against what's already stored (resume / re-run safe): adjacent clusters and
    # earlier runs can rediscover the same island, and we never delete existing rows.
    seen = {wkt for (wkt,) in db.session.query(RoadIsland.geometry_wkt).all()}
    initial_count = len(seen)
    logger.info(f"{len(seen)} road islands already in table")

    t0 = time.perf_counter()
    for i in range(start, len(clusters)):
        for poly in _road_islands_for_cluster(clusters[i]):
            wkt = poly.wkt
            if wkt not in seen:
                seen.add(wkt)
                db.session.add(RoadIsland(geometry_wkt=wkt))

        # Commit + checkpoint periodically so an interrupted run keeps its progress.
        if (i + 1) % COMMIT_EVERY == 0:
            db.session.commit()
            save_progress(NAME, i + 1)
            logger.info(f"  …{i + 1}/{len(clusters)} clusters, {len(seen)} islands ({time.perf_counter() - t0:.0f}s)")

    db.session.commit()
    if len(seen) != initial_count:
        mark_map_data_dirty()
    clear_checkpoint(NAME)
    logger.info(f"SYNC ROAD ISLANDS FINISHED — {len(seen)} islands in table")


main()
