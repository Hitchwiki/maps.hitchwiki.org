"""Build the `service_area` polygon table from OpenStreetMap.

For each cluster of nearby hitchhiking spots, fetch the gas-station / motorway-service /
rest-area / parking polygons in its bounding box and store each one's convex hull as WKT.
`show.py` then tests which spots actually fall inside a polygon and merges those into a
single spot, so the several pins people drop around one filling station collapse to one
marker. (We store all candidate polygons and let show.py do the point-in-polygon test —
the same division of labour as sync_road_islands — so one bbox query per cluster replaces
a per-spot `is_in`, roughly halving the Overpass load.)

Mirrors hitchmap's `fetch-areas.py`. A slow, resumable one-off — run manually (not via
cron; see the README), only when you want to refresh the polygons: throttled Overpass
calls, incremental commits, and a checkpoint so an interrupted run resumes.
Re-running upserts (never deletes) so previously-fetched polygons are never lost.
"""

import logging
import time

import shapely
from shapely.geometry import Polygon

from hitch.extensions import db
from hitch.models import ServiceArea
from hitch.scripts.osm_areas_common import (
    clear_checkpoint,
    cluster_bbox,
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

NAME = "sync_service_areas"
COMMIT_EVERY = 20  # clusters between DB commits + checkpoint saves

# Tags that mark a feature we want to group spots around.
AREA_TAG_MATCH = {
    ("amenity", "fuel"),
    ("highway", "services"),
    ("highway", "service_area"),
    ("highway", "rest_area"),
    ("highway", "parking"),
}


def _is_target_area(tags):
    return any((k, v) in AREA_TAG_MATCH for k, v in (tags or {}).items())


def _polygon_from_element(element):
    """Build the largest shapely Polygon from an Overpass element (way or relation).

    Ways carry a flat `geometry` node list; relations carry `members`, each with its
    own geometry — we take the member with the largest area. Rings with <3 points
    can't form a polygon and are skipped.
    """

    def ring(geometry):
        coords = [(pt["lon"], pt["lat"]) for pt in geometry or []]
        return Polygon(coords) if len(coords) >= 3 else None

    if element.get("type") == "relation":
        polys = [ring(m.get("geometry")) for m in element.get("members", [])]
        polys = [p for p in polys if p is not None and p.is_valid and p.area > 0]
        return max(polys, key=lambda p: p.area) if polys else None
    return ring(element.get("geometry"))


def _name_for(tags):
    tags = tags or {}
    if tags.get("official_name"):
        branch = tags.get("branch")
        return f"{tags['official_name']} {branch}".strip() if branch else tags["official_name"]
    return tags.get("name")


def main():
    logger.info("SYNC SERVICE AREAS SCRIPT STARTED")
    coords = load_spot_coords()
    clusters, start = resume_clusters(NAME, coords)

    t0 = time.perf_counter()
    for i in range(start, len(clusters)):
        south, west, north, east = cluster_bbox(clusters[i])
        bbox = f"{south},{west},{north},{east}"
        query = f"""
[out:json][timeout:60];
(
  way["amenity"="fuel"]({bbox});
  relation["amenity"="fuel"]({bbox});
  way["highway"~"services|service_area|rest_area|parking"]({bbox});
  relation["highway"~"services|service_area|rest_area|parking"]({bbox});
);
out geom;
"""
        for element in query_overpass(query):
            if not _is_target_area(element.get("tags")):
                continue
            poly = _polygon_from_element(element)
            if poly is None or not poly.is_valid or poly.area == 0:
                continue
            # Upsert by OSM id (PK) so re-runs refresh without dropping anything.
            db.session.merge(
                ServiceArea(
                    geom_id=element["id"],
                    name=_name_for(element.get("tags")),
                    geometry_wkt=shapely.convex_hull(poly).wkt,
                )
            )

        # Commit + checkpoint periodically so an interrupted run keeps its progress.
        if (i + 1) % COMMIT_EVERY == 0:
            db.session.commit()
            save_progress(NAME, i + 1)
            logger.info(
                f"  …{i + 1}/{len(clusters)} clusters, {db.session.query(ServiceArea).count()} areas "
                f"({time.perf_counter() - t0:.0f}s)"
            )

    db.session.commit()
    clear_checkpoint(NAME)
    logger.info(f"SYNC SERVICE AREAS FINISHED — {db.session.query(ServiceArea).count()} areas in table")


main()
