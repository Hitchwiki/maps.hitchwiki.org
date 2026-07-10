"""Seed of the routing engine.

For every ride in the DB that has both a start and a destination, fetch the
quickest driving route (OSRM) from start to destination, then work out which
*other* known starting points the route passes along the way. A starting point
counts as "passed" if it lies within PROXIMITY_M metres of the route polyline.

The output (dist/ride_routes.json) is essentially a first routing graph: for
each ride's corridor it lists the known hitchhiking start spots you travel past,
which is exactly the adjacency information a hitchhiking router needs ("if I get
this ride, which onward spots does it drop me near?").

Design notes / why it is written this way:
  * Reads the SQLite DB directly and only needs requests + numpy, so it runs on
    the minimal host venv (no Flask app context needed).
  * Routes are cached on disk (dist/route_cache.jsonl) keyed by rounded
    start/dest, so the job is fully resumable and re-runs cost nothing. OSRM's
    public server rate-limits, and fetching every route is the slow part.
  * Start coordinates are deduplicated into unique "spots" using the same
    lat.toFixed(5)_lon.toFixed(5) id convention as generate_spot_id/show.py, so
    the spatial join is over distinct anchors, not 22k raw points.
  * The "passed" test uses a grid index (cell ~= PROXIMITY_M) over the unique
    start spots so each route only compares against nearby spots instead of all
    of them — keeps the whole join roughly linear instead of O(rides * spots).
"""

import argparse
import json
import logging
import math
import os
import re
import sqlite3
import time
from datetime import datetime, timezone

import numpy as np
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# A start point is considered "passed" if within this distance of the route.
PROXIMITY_M = 300

# Merge start coordinates within this distance into one spot, matching show.py's
# MERGE_RADIUS_M single-linkage clustering so "the same spot" is identified the
# same way it is for dist/rides/. Needed so sequences from near-identical starts
# actually overlap.
MERGE_RADIUS_M = 5

# A downstream sequence must be shared by at least this many rides to count as a
# repeatable route (excludes long one-off rides we have no evidence repeat).
MIN_SUPPORT = 2

# The routers fall back to a graph built without that threshold when the
# repeatable one connects nothing: one person's single logged ride is weak
# evidence, but it beats telling the user "no route found".
FALLBACK_MIN_SUPPORT = 1

# Grid cell size for the spatial index, in degrees. ~0.003 deg latitude ~= 330 m,
# so a 1-ring (3x3) neighbourhood always covers the PROXIMITY_M search radius.
CELL_DEG = 0.003

OSRM_URL = "https://router.project-osrm.org/route/v1/driving/{coords}"

EARTH_RADIUS_M = 6371000.0


def get_dist_dir():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(root, "dist")


def get_db_path():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    db_name = os.environ.get("DATABASE_NAME", "hitchhiking-prod.sqlite")
    return os.path.join(root, "db", db_name)


def spot_id(lat, lon):
    # Matches generate_spot_id / the frontend: 5 decimals (~1.1 m).
    return f"{lat:.5f}_{lon:.5f}"


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres. Scalars or numpy arrays."""
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    return EARTH_RADIUS_M * 2 * np.arcsin(np.sqrt(a))


def load_rides(db_path):
    """Return every ride that has a valid start location.

    `dest` is the last stop when it's a distinct valid location, else None. The
    start-spot universe (and its consolidation) is built from ALL such rides so
    it matches show.py's map spots; only rides with a `dest` are actually routed.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, stops FROM ride_event").fetchall()
    conn.close()

    rides = []
    for r in rows:
        stops = r["stops"]
        if isinstance(stops, str):
            try:
                stops = json.loads(stops)
            except (ValueError, TypeError):
                continue
        if not stops:
            continue
        try:
            s = stops[0]["location"]
            slat, slon = s["latitude"], s["longitude"]
        except (KeyError, TypeError, IndexError):
            continue
        if slat is None or slon is None:
            continue
        dest = None
        if len(stops) > 1:
            try:
                d = stops[-1]["location"]
                dlat, dlon = d["latitude"], d["longitude"]
                # Skip degenerate rides where start == destination (no route to draw).
                if dlat is not None and dlon is not None and not (abs(slat - dlat) < 1e-6 and abs(slon - dlon) < 1e-6):
                    dest = (float(dlat), float(dlon))
            except (KeyError, TypeError, IndexError):
                pass
        rides.append(
            {
                "id": r["id"],
                "start": (float(slat), float(slon)),
                "dest": dest,
                # Waiting time (minutes) the hitchhiker waited to get this ride, from
                # the first stop — same field show.py reads. None when not recorded.
                "wait": parse_wait(stops[0].get("waiting_duration")),
            }
        )
    return rides


def parse_wait(iso):
    """ISO 8601 duration (e.g. 'PT30M', 'PT1H15M') -> minutes, or None."""
    if not iso or not isinstance(iso, str):
        return None
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?", iso.strip())
    if not m or (m.group(1) is None and m.group(2) is None):
        return None
    return int(m.group(1) or 0) * 60 + int(m.group(2) or 0)


# ---------------------------------------------------------------------------
# Route fetching (with on-disk cache)
# ---------------------------------------------------------------------------


def _route_key(start, dest):
    # 4 decimals (~11 m) is plenty to dedupe near-identical endpoints.
    return f"{start[0]:.4f},{start[1]:.4f};{dest[0]:.4f},{dest[1]:.4f}"


def index_route_cache(path):
    """Return {key: byte_offset} without parsing geometry.

    The cache holds ~17k routes, each a polyline of thousands of points — loading
    them all into RAM at once costs multiple GB and OOM-kills the process. Instead
    we index each line's offset and read one route's geometry on demand (see
    read_cached_route), keeping only a single geometry in memory at a time.
    """
    index = {}
    if not os.path.exists(path):
        return index
    with open(path, "rb") as f:
        offset = 0
        for raw in f:
            stripped = raw.strip()
            if stripped:
                try:
                    rec = json.loads(stripped)
                    index[rec["key"]] = offset
                except ValueError:
                    pass
            offset += len(raw)
    return index


def read_cached_route(read_handle, offset):
    read_handle.seek(offset)
    return json.loads(read_handle.readline())["route"]


def fetch_route(start, dest, session, sleep, retries=3):
    """Query OSRM for the fastest driving route. Returns dict or None on failure.

    OSRM expects lon,lat order. geometry is a list of [lat, lon] pairs.
    """
    coords = f"{start[1]},{start[0]};{dest[1]},{dest[0]}"
    url = OSRM_URL.format(coords=coords)
    params = {"overview": "full", "geometries": "geojson", "alternatives": "false"}
    for attempt in range(retries):
        try:
            resp = session.get(url, params=params, timeout=30)
            if resp.status_code == 429:
                # Rate limited — back off and retry.
                time.sleep(2 + attempt * 2)
                continue
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != "Ok" or not data.get("routes"):
                return None
            route = data["routes"][0]
            # geojson coords are [lon, lat]; store as [lat, lon] to match everything else.
            geom = [[c[1], c[0]] for c in route["geometry"]["coordinates"]]
            return {
                "distance_m": round(route["distance"], 1),
                "duration_s": round(route["duration"], 1),
                "geometry": geom,
            }
        except (requests.RequestException, ValueError):
            time.sleep(1 + attempt)
        finally:
            if sleep:
                time.sleep(sleep)
    return None


# ---------------------------------------------------------------------------
# Spatial index over unique start spots
# ---------------------------------------------------------------------------


def cell_of(lat, lon):
    return (int(math.floor(lat / CELL_DEG)), int(math.floor(lon / CELL_DEG)))


def build_spot_index(spots):
    """spots: dict spot_id -> {lat, lon, ride_ids}. Returns grid dict cell -> [spot_id]."""
    grid = {}
    for sid, s in spots.items():
        grid.setdefault(cell_of(s["lat"], s["lon"]), []).append(sid)
    return grid


def merge_spots(raw):
    """Single-linkage merge of start spots within MERGE_RADIUS_M.

    Replicates show.py's DBSCAN(min_samples=1) clustering — which is just the
    connected components of the graph joining points closer than the radius —
    using a small grid + union-find (no sklearn needed on the host). Each cluster
    is anchored to its busiest member (ties broken by lat then lon, matching
    show.py), so the canonical spot id / coordinate is stable.

    raw: dict raw_spot_id -> {lat, lon, ride_ids}.
    Returns (merged_spots, remap) where merged_spots is keyed by anchor spot id
    and remap maps every raw_spot_id to its anchor spot id.
    """
    ids = list(raw.keys())
    n = len(ids)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Grid at the merge radius so only genuinely-close pairs are ever compared.
    cell_deg = MERGE_RADIUS_M / (EARTH_RADIUS_M * math.pi / 180.0)
    grid = {}
    coords = [(raw[s]["lat"], raw[s]["lon"]) for s in ids]
    for i, (lat, lon) in enumerate(coords):
        grid.setdefault((int(lat / cell_deg), int(lon / cell_deg)), []).append(i)

    for i, (lat, lon) in enumerate(coords):
        cy, cx = int(lat / cell_deg), int(lon / cell_deg)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for j in grid.get((cy + dy, cx + dx), ()):
                    if j > i and haversine_m(lat, lon, coords[j][0], coords[j][1]) <= MERGE_RADIUS_M:
                        union(i, j)

    # Gather cluster members, then pick each anchor (busiest, then lat, then lon).
    clusters = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(i)

    merged = {}
    remap = {}
    for members in clusters.values():
        anchor_i = min(members, key=lambda i: (-len(raw[ids[i]]["ride_ids"]), coords[i][0], coords[i][1]))
        anchor_lat, anchor_lon = coords[anchor_i]
        anchor_id = spot_id(anchor_lat, anchor_lon)
        ride_ids = []
        for i in members:
            ride_ids.extend(raw[ids[i]]["ride_ids"])
            remap[ids[i]] = anchor_id
        merged[anchor_id] = {"lat": anchor_lat, "lon": anchor_lon, "ride_ids": ride_ids}
    return merged, remap


def polygon_merge(spots, db_path):
    """Coarser grouping on top of the 5 m merge, matching show.py exactly.

    Spots inside the same OSM service area (gas station / rest stop) or the same
    road island are the same physical hitchhiking spot even when tens of metres
    apart — e.g. both sides of a motorway rest area. Without this the two sides
    stay separate in the routing graph, so a spot only "knows" the rides that
    started on its own side and corridors dead-end. We assign each spot the
    containing polygon (service area wins over road island; largest wins on
    overlap) and re-anchor every polygon to its busiest member, so the resulting
    spot ids/coordinates line up with show.py's map spots.

    spots: dict spot_id -> {lat, lon, ride_ids} (the 5 m-merge output).
    Returns (merged_spots, remap) with remap mapping each input id to its anchor.
    """
    try:
        from shapely import STRtree
        from shapely.geometry import Point
        from shapely.wkt import loads as wkt_loads
    except ImportError:
        # shapely isn't on the host venv; run this script in the container to get
        # the polygon grouping. Fall back to the 5 m merge only so it still runs.
        logger.warning("shapely not available — skipping service-area/road-island grouping (run in container)")
        return spots, {sid: sid for sid in spots}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        sa_rows = conn.execute("SELECT geom_id, geometry_wkt FROM service_area").fetchall()
        ri_rows = conn.execute("SELECT id, geometry_wkt FROM road_island").fetchall()
    except sqlite3.OperationalError:
        logger.warning("service_area / road_island tables not found — skipping polygon grouping")
        conn.close()
        return spots, {sid: sid for sid in spots}
    conn.close()

    ids = list(spots.keys())
    coords = [(spots[s]["lat"], spots[s]["lon"]) for s in ids]
    # Polygons were built in (lon, lat) order, so query points must match.
    points = [Point(lon, lat) for lat, lon in coords]

    def assign_polygon(rows, id_key):
        geoms = [wkt_loads(r["geometry_wkt"]) for r in rows]
        poly_ids = [r[id_key] for r in rows]
        if not geoms:
            return [None] * len(points)
        tree = STRtree(geoms)
        areas = [g.area for g in geoms]
        out = []
        for pt in points:
            cand = tree.query(pt, predicate="within")
            out.append(poly_ids[max(cand, key=lambda idx: areas[idx])] if len(cand) else None)
        return out

    sa_ids = assign_polygon(sa_rows, "geom_id")
    ri_ids = assign_polygon(ri_rows, "id")

    # One grouping label per spot; service area beats road island, points in
    # neither keep their own coordinate (the 5 m-merge result).
    labels = []
    for sa_id, ri_id, sid in zip(sa_ids, ri_ids, ids):
        if sa_id is not None:
            labels.append(f"sa:{sa_id}")
        elif ri_id is not None:
            labels.append(f"ri:{ri_id}")
        else:
            labels.append(f"pt:{sid}")

    # Members per label, then anchor on the busiest (ride count, ties lat/lon).
    members_by_label = {}
    for i, lbl in enumerate(labels):
        members_by_label.setdefault(lbl, []).append(i)

    merged = {}
    remap = {}
    n_poly = 0
    for lbl, members in members_by_label.items():
        if not lbl.startswith("pt:"):
            n_poly += 1
        anchor_i = min(members, key=lambda i: (-len(spots[ids[i]]["ride_ids"]), coords[i][0], coords[i][1]))
        anchor_lat, anchor_lon = coords[anchor_i]
        anchor_id = spot_id(anchor_lat, anchor_lon)
        ride_ids = []
        for i in members:
            ride_ids.extend(spots[ids[i]]["ride_ids"])
            remap[ids[i]] = anchor_id
        merged[anchor_id] = {"lat": anchor_lat, "lon": anchor_lon, "ride_ids": ride_ids}
    logger.info("Polygon grouping collapsed %d spots into %d service-area/road-island spots", len(ids) - len(merged), n_poly)
    return merged, remap


# Max distance a routing spot may be snapped onto a map spot. Needs to cover the
# span of a big motorway rest area (both sides can be ~200 m apart) but stay well
# under the gap between genuinely distinct spots.
SNAP_TO_MAP_M = 250


def snap_to_map_spots(spots, dist_dir):
    """Snap every routing spot onto the nearest spot show.py actually published in
    dist/spots.json, adopting the map's exact coordinate/id.

    Our own 5 m + polygon consolidation gets close to the map's spots but can
    still diverge (a different busiest-member anchor lands just outside a
    service-area polygon, so a rest area splits into a phantom spot with no map
    pin). Snapping to the published spots guarantees every boarding / change spot
    in a route is a real, clickable map marker with its rides — which is the whole
    point of using the same spots as the map.

    Returns (snapped_spots, remap). Spots with no map spot within SNAP_TO_MAP_M
    (rare) keep their own coordinate so the network isn't silently truncated.
    """
    try:
        with open(os.path.join(dist_dir, "spots.json"), encoding="utf-8") as f:
            map_spots = json.load(f)
    except (OSError, ValueError):
        logger.warning("dist/spots.json not found — skipping snap-to-map-spots")
        return spots, {sid: sid for sid in spots}

    # Grid index of map spots at the snap radius so lookups only test nearby pins.
    cell_deg = SNAP_TO_MAP_M / (EARTH_RADIUS_M * math.pi / 180.0)
    grid = {}
    for ms in map_spots:
        grid.setdefault((int(ms["lat"] / cell_deg), int(ms["lon"] / cell_deg)), []).append(ms)

    def nearest_map(lat, lon):
        cy, cx = int(lat / cell_deg), int(lon / cell_deg)
        best, best_d = None, SNAP_TO_MAP_M
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for ms in grid.get((cy + dy, cx + dx), ()):
                    d = haversine_m(lat, lon, ms["lat"], ms["lon"])
                    if d <= best_d:
                        best, best_d = ms, d
        return best

    snapped = {}
    remap = {}
    for sid, s in spots.items():
        ms = nearest_map(s["lat"], s["lon"])
        if ms is None:
            tlat, tlon = s["lat"], s["lon"]
        else:
            tlat, tlon = ms["lat"], ms["lon"]
        tid = spot_id(tlat, tlon)
        remap[sid] = tid
        tgt = snapped.setdefault(tid, {"lat": tlat, "lon": tlon, "ride_ids": []})
        tgt["ride_ids"].extend(s["ride_ids"])
    logger.info("Snapped %d routing spots onto %d map spots", len(spots), len(snapped))
    return snapped, remap


def build_repeatable_trees(rides, spots, min_support=MIN_SUPPORT):
    """For each start spot, build a prefix tree of its rides' downstream spot
    sequences and prune every path shared by fewer than `min_support` rides.

    A node's support = the number of rides whose sequence shares the whole path
    from the start up to that node. Support only decreases along a path, so
    dropping sub-threshold nodes truncates a long one-off ride to the prefix it
    shares with others — exactly the "only keep the overlapping part" rule.
    At min_support=1 nothing is pruned and every ride contributes its full
    sequence: the superset graph the routers fall back to.

    Each node is [spot_idx, parent_idx, support, wait_min] for each start spot
    that has at least one surviving edge. parent_idx indexes into the same nodes
    list, or -1 for a direct child of the start spot. wait_min is the average
    waiting time (minutes) of all rides whose route used that edge (null if none
    of them recorded a wait) — added so the router can model hitchhiking waits.
    """
    spot_ids = list(spots.keys())
    spot_index = {sid: i for i, sid in enumerate(spot_ids)}

    # Group the passed-spot sequences by (merged) start spot, and accumulate the
    # waiting time each ride contributes to every consecutive spot-pair (edge) of
    # its route. A ride "uses" edge (u, v) when u, v are consecutive spots in its
    # start-prefixed sequence; its wait is averaged over all such rides.
    sequences_by_start = {}
    edge_wait_sum = {}
    edge_wait_count = {}
    for ride in rides:
        if not ride.get("routed"):
            continue
        seq = [sid for sid, _dmin, _idx in ride["passed"]]
        if seq:
            sequences_by_start.setdefault(ride["start_spot_id"], []).append(seq)
        wait = ride.get("wait")
        if wait is None:
            continue
        full = [ride["start_spot_id"], *seq]
        for u, v in zip(full, full[1:]):
            if u == v:
                continue
            edge_wait_sum[(u, v)] = edge_wait_sum.get((u, v), 0) + wait
            edge_wait_count[(u, v)] = edge_wait_count.get((u, v), 0) + 1

    def edge_wait(u_sid, v_sid):
        n = edge_wait_count.get((u_sid, v_sid))
        return round(edge_wait_sum[(u_sid, v_sid)] / n, 1) if n else None

    def walk(node, parent_idx, nodes):
        for child in node["children"].values():
            if child["count"] < min_support:
                continue
            idx = len(nodes)
            nodes.append([
                spot_index[child["spot"]],
                parent_idx,
                child["count"],
                edge_wait(node["spot"], child["spot"]),
            ])
            walk(child, idx, nodes)

    trees = []
    for start_sid, sequences in sequences_by_start.items():
        if len(sequences) < min_support:
            continue  # can't have a shared path with fewer than min_support rides

        # Trie node: {"spot": sid, "count": int, "children": {sid: node}}.
        root = {"spot": start_sid, "count": len(sequences), "children": {}}
        for seq in sequences:
            cur = root
            for sid in seq:
                child = cur["children"].get(sid)
                if child is None:
                    child = {"spot": sid, "count": 0, "children": {}}
                    cur["children"][sid] = child
                child["count"] += 1
                cur = child

        # Flatten surviving nodes (support >= min_support) into a parent-linked list.
        nodes = []
        walk(root, -1, nodes)
        if nodes:
            trees.append({"s": spot_index[start_sid], "nodes": nodes})
    return trees


def passed_spots_for_route(geometry, spots, grid, own_spot_id):
    """Return spot ids within PROXIMITY_M of the route polyline.

    Candidates are gathered from the grid cells the route vertices touch (plus a
    1-ring border), then verified with an exact vertex-distance check. OSRM's
    full geometry is densely sampled (tens of metres between vertices), so
    nearest-vertex distance is an accurate proxy for distance-to-polyline at the
    300 m scale.
    """
    geom = np.asarray(geometry, dtype=float)  # (N, 2) lat, lon

    # Candidate spot ids: every spot sitting in a cell touched by the route or
    # its immediate neighbours.
    candidate_ids = set()
    touched = set()
    for lat, lon in geom:
        touched.add(cell_of(lat, lon))
    for cy, cx in touched:
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                candidate_ids.update(grid.get((cy + dy, cx + dx), ()))

    candidate_ids.discard(own_spot_id)
    if not candidate_ids:
        return []

    vlat = geom[:, 0]
    vlon = geom[:, 1]
    passed = []
    for sid in candidate_ids:
        s = spots[sid]
        dists = haversine_m(s["lat"], s["lon"], vlat, vlon)
        idx = int(np.argmin(dists))
        dmin = float(dists[idx])
        if dmin <= PROXIMITY_M:
            # idx = index of the nearest route vertex => how far along the route
            # the spot sits, used to draw the connecting line in route order.
            passed.append((sid, dmin, idx))
    # Order along the route (by progression), not by distance, so a line through
    # the passed spots follows the direction of travel start -> destination.
    passed.sort(key=lambda t: t[2])
    return passed


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None, help="only process the first N rides (default: all)")
    ap.add_argument("--sleep", type=float, default=0.1, help="delay between OSRM requests, seconds")
    ap.add_argument("--include-geometry", action="store_true", help="include full route geometry in output")
    ap.add_argument(
        "--skip-detailed",
        action="store_true",
        help="only write the compact test file, skip the big ride_routes.json (lower memory)",
    )
    args = ap.parse_args()

    dist_dir = get_dist_dir()
    os.makedirs(dist_dir, exist_ok=True)
    cache_path = os.path.join(dist_dir, "route_cache.jsonl")
    out_path = os.path.join(dist_dir, "ride_routes.json")

    all_rides = load_rides(get_db_path())
    logger.info("Loaded %d rides with a valid start (%d also routable)", len(all_rides), sum(1 for r in all_rides if r["dest"]))

    # Build the universe of unique start spots (deduped by 5-decimal coord id)
    # from ALL rides — a route can pass any known start point, not only ones in
    # the routed subset. --limit only restricts which rides we fetch routes for.
    raw_spots = {}
    for ride in all_rides:
        slat, slon = ride["start"]
        sid = spot_id(slat, slon)
        ride["start_spot_id"] = sid
        spot = raw_spots.setdefault(sid, {"lat": slat, "lon": slon, "ride_ids": []})
        spot["ride_ids"].append(ride["id"])
    logger.info("Found %d unique start coordinates", len(raw_spots))

    # Consolidate spots EXACTLY as show.py does so the routing graph's spots are
    # the map's spots: (1) 5 m single-linkage merge, then (2) service-area /
    # road-island polygon grouping. Compose the two remaps and reassign every
    # ride's start id, so passed spots and start spots share one canonical
    # identity (e.g. both sides of a rest area become one spot with all directions).
    spots, remap1 = merge_spots(raw_spots)
    logger.info("Merged into %d start spots (within %d m)", len(spots), MERGE_RADIUS_M)
    spots, remap2 = polygon_merge(spots, get_db_path())
    logger.info("After polygon grouping: %d spots", len(spots))
    # Final stage: adopt show.py's published spot coordinates so every routing
    # spot is a real, clickable map marker (fixes phantom spots off the map).
    spots, remap3 = snap_to_map_spots(spots, dist_dir)
    remap = {sid: remap3[remap2[remap1[sid]]] for sid in raw_spots}
    for ride in all_rides:
        ride["start_spot_id"] = remap[ride["start_spot_id"]]
    grid = build_spot_index(spots)

    # Only rides with a destination can be routed; the rest just seed the spot set.
    rides = [r for r in all_rides if r["dest"]]
    if args.limit:
        rides = rides[: args.limit]
    logger.info("Routing %d rides against all %d start spots", len(rides), len(spots))

    cache_index = index_route_cache(cache_path)
    logger.info("Indexed %d cached routes", len(cache_index))

    session = requests.Session()
    session.headers.update({"User-Agent": "hitchwiki-routing-engine/0.1"})

    results = []
    fetched = 0
    failed = 0
    with open(cache_path, "a", encoding="utf-8") as cache_file, open(cache_path, encoding="utf-8") as read_handle:
        for i, ride in enumerate(rides):
            key = _route_key(ride["start"], ride["dest"])
            if key in cache_index:
                route = read_cached_route(read_handle, cache_index[key])
            else:
                route = fetch_route(ride["start"], ride["dest"], session, args.sleep)
                if route is not None:
                    # Record the new line's offset before appending, so later
                    # rides sharing these endpoints read it back from the cache.
                    cache_file.seek(0, os.SEEK_END)
                    cache_index[key] = cache_file.tell()
                    cache_file.write(json.dumps({"key": key, "route": route}) + "\n")
                    cache_file.flush()
                    fetched += 1
                else:
                    failed += 1
            if route is None:
                continue

            passed = passed_spots_for_route(route["geometry"], spots, grid, ride["start_spot_id"])
            # Keep the raw result on the ride for the compact test file below.
            ride["passed"] = passed
            ride["route_dist_m"] = route["distance_m"]
            ride["routed"] = True
            passed_out = [
                {
                    "spot_id": sid,
                    "lat": spots[sid]["lat"],
                    "lon": spots[sid]["lon"],
                    "dist_m": round(dmin, 1),
                    "ride_ids": spots[sid]["ride_ids"],
                }
                for sid, dmin, _ in passed
            ]

            if not args.skip_detailed:
                entry = {
                    "id": ride["id"],
                    "start": {"lat": ride["start"][0], "lon": ride["start"][1], "spot_id": ride["start_spot_id"]},
                    "destination": {"lat": ride["dest"][0], "lon": ride["dest"][1]},
                    "route": {
                        "distance_m": route["distance_m"],
                        "duration_s": route["duration_s"],
                        "num_points": len(route["geometry"]),
                    },
                    "passed_start_count": len(passed_out),
                    "passed_starts": passed_out,
                }
                if args.include_geometry:
                    entry["route"]["geometry"] = route["geometry"]
                results.append(entry)

            if (i + 1) % 100 == 0:
                logger.info("Processed %d/%d rides (fetched %d, failed %d)", i + 1, len(rides), fetched, failed)

    if not args.skip_detailed:
        output = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "proximity_m": PROXIMITY_M,
            "ride_count": len(results),
            "unique_start_spots": len(spots),
            "routes_fetched": fetched,
            "routes_failed": failed,
            "rides": results,
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f)
        logger.info("Wrote %s: %d rides, %d fetched, %d failed", out_path, len(results), fetched, failed)
    else:
        logger.info("Skipped detailed output (%d fetched, %d failed)", fetched, failed)

    write_test_file(dist_dir, rides, spots)
    write_repeatable_file(dist_dir, rides, spots)
    write_oneoff_file(dist_dir, rides, spots)


def write_test_file(dist_dir, rides, spots):
    """Emit a compact dist/test_routes.json for the lightweight /test map.

    Coordinates are indexed (a ride references spots by integer index) and
    rounded to 5 decimals to keep the payload small. Structure:
      spots:      [[lat, lon], ...]                unique start spots
      spot_rides: [[ride_idx, ...], ...]           rides starting at each spot
      rides:      [{s, d:[lat,lon], km, p:[spot_idx,...]}, ...]
                    s  = start spot index
                    d  = destination [lat, lon]
                    km = route distance in km
                    p  = passed start-spot indices, ordered along the route
    """
    out_path = os.path.join(dist_dir, "test_routes.json")

    # Stable spot ordering + id -> index lookup.
    spot_ids = list(spots.keys())
    spot_index = {sid: i for i, sid in enumerate(spot_ids)}
    spots_out = [[round(spots[sid]["lat"], 5), round(spots[sid]["lon"], 5)] for sid in spot_ids]

    rides_out = []
    spot_rides = [[] for _ in spot_ids]
    for ride in rides:
        if not ride.get("routed"):
            continue
        s_idx = spot_index[ride["start_spot_id"]]
        ride_idx = len(rides_out)
        spot_rides[s_idx].append(ride_idx)
        rides_out.append(
            {
                "s": s_idx,
                "d": [round(ride["dest"][0], 5), round(ride["dest"][1], 5)],
                "km": round(ride["route_dist_m"] / 1000, 1),
                "p": [spot_index[sid] for sid, _dmin, _idx in ride["passed"]],
            }
        )

    test = {"proximity_m": PROXIMITY_M, "spots": spots_out, "spot_rides": spot_rides, "rides": rides_out}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(test, f, separators=(",", ":"))
    logger.info(
        "Wrote %s: %d spots, %d rides (%.1f MB)", out_path, len(spots_out), len(rides_out), os.path.getsize(out_path) / 1e6
    )


def write_repeatable_file(dist_dir, rides, spots):
    """Emit dist/repeatable_routes.json: per start spot, the downstream spot
    sequences shared by at least MIN_SUPPORT rides (see build_repeatable_trees).

    Uses the same spot ordering as test_routes.json (both derive it from
    list(spots.keys()) in this process), so spot indices are interchangeable
    between the two files.
    """
    out_path = os.path.join(dist_dir, "repeatable_routes.json")
    spot_ids = list(spots.keys())
    spots_out = [[round(spots[sid]["lat"], 5), round(spots[sid]["lon"], 5)] for sid in spot_ids]

    trees = build_repeatable_trees(rides, spots)
    edge_count = sum(len(t["nodes"]) for t in trees)

    data = {"proximity_m": PROXIMITY_M, "min_support": MIN_SUPPORT, "spots": spots_out, "trees": trees}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    logger.info(
        "Wrote %s: %d start spots with repeatable routes, %d edges (%.1f MB)",
        out_path,
        len(trees),
        edge_count,
        os.path.getsize(out_path) / 1e6,
    )


def write_oneoff_file(dist_dir, rides, spots):
    """Emit dist/oneoff_routes.json: the same corridor trees built with no support
    threshold, so a sequence only one ride ever took still forms edges.

    This is the routers' second pass, searched only when the repeatable graph
    connects nothing (see routing.js `loadFallbackRouter`, repeatable_router.py
    `load_oneoff_router`). It's a superset of repeatable_routes.json's trees and
    ~6x its size, which is why it lives in its own lazily fetched file.

    Spot coordinates are deliberately omitted: the indices address the `spots`
    array of repeatable_routes.json, which the same run writes from the same
    dict. `spot_count` lets a reader detect the half-regenerated case (one file
    stale) and refuse the data rather than draw a route through wrong spots.
    """
    out_path = os.path.join(dist_dir, "oneoff_routes.json")

    trees = build_repeatable_trees(rides, spots, min_support=FALLBACK_MIN_SUPPORT)
    edge_count = sum(len(t["nodes"]) for t in trees)

    data = {
        "proximity_m": PROXIMITY_M,
        "min_support": FALLBACK_MIN_SUPPORT,
        "spot_count": len(spots),
        "trees": trees,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    logger.info(
        "Wrote %s: %d start spots with one-off routes, %d edges (%.1f MB)",
        out_path,
        len(trees),
        edge_count,
        os.path.getsize(out_path) / 1e6,
    )


if __name__ == "__main__":
    main()
