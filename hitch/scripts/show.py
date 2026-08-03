import contextlib
import json
import logging
import math
import os
import shutil
import sqlite3
import time
import warnings

import numpy as np
import pandas as pd
from flask import current_app
from shapely import STRtree
from shapely.geometry import Point
from shapely.wkt import loads as wkt_loads
from sklearn.cluster import DBSCAN
from sklearn.exceptions import InconsistentVersionWarning

from hitch.blueprints.utils.notifications import load_race_podiums, notify_new_race_podiums
from hitch.blueprints.utils.report_ride import OWNER_DELETE_REASON, REPORTS_TO_HIDE
from hitch.blueprints.utils.ride_images import image_url
from hitch.helpers import e, get_bearing, get_db, get_dirs, haversine_np, write_json_file
from hitch.scripts.races import build_races, estimate_arrival
from hitch.scripts.spot_naming import resolve_spot_name
from hitch.scripts.spots_gpx import spot_waypoint, write_spots_gpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

dirs = get_dirs()

logger.info("Creating directories if they don't exist")
os.makedirs(dirs["dist"], exist_ok=True)


# Check if we need to regenerate JSON files
def should_regenerate_json():
    """Check if JSON files need regeneration based on database modification time."""
    db_path = current_app.config["DATABASE_URI"]

    # Check if database exists
    if not os.path.exists(db_path):
        logger.warning(f"Database file not found: {db_path}")
        return True

    db_mtime = os.path.getmtime(db_path)

    # Check each JSON file
    # races.json is deliberately absent: it is rebuilt on its own hourly schedule further
    # down, so its age must not decide whether the rest of the map data is regenerated.
    # spots.gpx is in the list (despite the name) so that a deploy that adds it, or a
    # dist/ that lost it, regenerates on the next run instead of leaving the menu's
    # download link 404ing until the next ride lands.
    json_files = [
        "spots.json",
        "rides_index.json",
        "spots_recent.json",
        "longest_rides.json",
        "longest_24h.json",
        "spots.gpx",
    ]

    # Per-spot ride directory — treat the dir itself as the canary.
    by_spot_dir = os.path.join(dirs["dist"], "rides", "by-spot")
    if not os.path.isdir(by_spot_dir):
        logger.info("Regeneration needed: rides/by-spot directory is missing")
        return True

    # A new or retuned race in RACES.md must reach the page without waiting for the next
    # ride to land: the DB mtime alone would never notice a config-only change.
    races_json = os.path.join(dirs["dist"], "races.json")
    races_md = os.path.join(dirs["root"], "RACES.md")
    if os.path.exists(races_md) and (not os.path.exists(races_json) or os.path.getmtime(races_md) > os.path.getmtime(races_json)):
        logger.info("Regeneration needed: RACES.md is newer than races.json")
        return True

    # Only check heatmap if it's enabled
    if current_app.config.get("GENERATE_HEATMAP", True):
        json_files.append("heatmap.json")

    for json_file in json_files:
        json_path = os.path.join(dirs["dist"], json_file)
        if not os.path.exists(json_path):
            logger.info(f"Regeneration needed: {json_file} is missing")
            return True
        elif os.path.getmtime(json_path) < db_mtime:
            logger.info(f"Regeneration needed: {json_file} is outdated")
            return True

    return False


# Skip processing if JSON files are up to date (unless forced)
if not current_app.config.get("FORCE_REGENERATE", False) and not should_regenerate_json():
    logger.info("JSON files are up to date, skipping regeneration")
    logger.info("SHOW SCRIPT FINISHED")
    exit(0)

logger.info("Database has been updated, regenerating JSON files")
logger.info("Fetching rides")
# Instant every generated file below is derived from. Captured BEFORE the read, not
# after the writes: /pending_rides.json serves rides created at or after this timestamp,
# and a ride landing while this script runs must count as pending rather than be
# silently skipped by a cutoff taken once the files are already on disk.
snapshot_ts = time.time()
rides_df = pd.read_sql("select * from ride_event", get_db())
logger.info(f"Got {len(rides_df)} rides")


def get_reported_dtags():
    """Nostr d-tags of rides hidden by community reports.

    A ride is hidden once at least REPORTS_TO_HIDE distinct users have reported it for
    the same reason. Reports are unique per (ride, user), so each row is a distinct
    person, making the per-reason count a count of distinct reporters. An owner-deletion
    row bypasses the threshold: one is enough, since only the ride's author can write it.
    Returns an empty set if the ride_report table doesn't exist yet (e.g. a DB that
    predates the feature).
    """
    try:
        reported = pd.read_sql(
            "select ride_d_tag from ride_report group by ride_d_tag, reason "
            f"having count(*) >= {REPORTS_TO_HIDE} or reason = '{OWNER_DELETE_REASON}'",
            get_db(),
        )
    except pd.errors.DatabaseError:
        return set()
    return set(reported["ride_d_tag"])


# Drop reported rides up front so they're excluded from every downstream output
# (spots aggregation, per-spot files, rides_index, recent).
reported_dtags = get_reported_dtags()
if reported_dtags:
    before = len(rides_df)
    rides_df = rides_df[~rides_df["d"].isin(reported_dtags)].reset_index(drop=True)
    logger.info(f"Excluded {before - len(rides_df)} reported ride(s) across {len(reported_dtags)} d-tag(s)")

rides_df["stops"] = rides_df["stops"].apply(lambda x: json.loads(x) if isinstance(x, str) else x)
rides_df["hitchhikers"] = rides_df["hitchhikers"].apply(lambda x: json.loads(x) if isinstance(x, str) else x)
rides_df["mode_of_transportation"] = rides_df["mode_of_transportation"].apply(
    lambda x: json.loads(x) if isinstance(x, str) else x
)
# SQLite returns the JSON column as a string; parse it so get_signals /
# get_signal_methods (which require a list of approach dicts) actually see
# the data instead of silently returning None.
rides_df["signals"] = rides_df["signals"].apply(lambda x: json.loads(x) if isinstance(x, str) else x)


def _has_distinct_destination(stops):
    """True if the ride already reached a stop distinct from its start."""
    if not isinstance(stops, list) or len(stops) < 2:
        return False
    start = (stops[0] or {}).get("location") or {}
    for s in stops[1:]:
        loc = (s or {}).get("location") or {}
        if loc.get("latitude") is None or loc.get("longitude") is None:
            continue
        if abs(loc["latitude"] - start.get("latitude", 0)) > 1e-6 or abs(loc["longitude"] - start.get("longitude", 0)) > 1e-6:
            return True
    return False


def merge_derived_destinations(df):
    """Append destinations we mined from comment text (derived_ride_location, keyed by the
    ride's Nostr `d` tag) as an extra stop on rides that reached Nostr without one. These
    are inferred from prose, not logged GPS fixes, so they carry is_exact=False. Doing it
    here means every downstream view (spots dest lines, distance, routing input) treats a
    derived destination exactly like a real last stop. See hitch/scripts/extract_destinations.py."""
    # Flag rides whose destination we inferred from prose rather than one the user logged, so
    # leaderboards that rank by distance can exclude them — a mis-geocoded derived destination
    # must never win "longest ride". Downstream map views still treat it like a real last stop.
    # Set unconditionally (even on the early returns below) so the column always exists.
    df["dest_is_derived"] = False
    try:
        derived = pd.read_sql("select d, latitude, longitude, is_exact from derived_ride_location", get_db())
    except pd.errors.DatabaseError:
        return 0  # table absent on DBs that predate the enrichment
    by_d = {r.d: (r.latitude, r.longitude, bool(r.is_exact)) for r in derived.itertuples()}
    if not by_d:
        return 0
    merged = 0
    for i, row in df.iterrows():
        loc = by_d.get(row["d"])
        if not loc or _has_distinct_destination(row["stops"]):
            continue
        stops = list(row["stops"]) if isinstance(row["stops"], list) else []
        if not stops:
            continue  # need a start stop to anchor the ride
        stops.append({"location": {"latitude": loc[0], "longitude": loc[1], "is_exact": loc[2]}})
        df.at[i, "stops"] = stops
        df.at[i, "dest_is_derived"] = True
        merged += 1
    return merged


_merged = merge_derived_destinations(rides_df)
logger.info(f"Merged {_merged} derived destination(s) from comment text")


def merge_derived_waits(df):
    """Fill in waiting times we mined from comment text (derived_ride_wait, keyed by the
    ride's Nostr `d` tag) on rides that reached Nostr without a `waiting_duration`. Written
    as ISO 8601 on the first stop, exactly the shape get_wait() already reads, so every
    downstream wait view (spot averages, heatmap, routing) treats a derived wait like a
    logged one. Never overwrites a wait the ride already carries. See
    hitch/scripts/extract_wait_times.py."""
    try:
        derived = pd.read_sql("select d, waiting_minutes from derived_ride_wait", get_db())
    except pd.errors.DatabaseError:
        return 0  # table absent on DBs that predate the enrichment
    by_d = {r.d: int(r.waiting_minutes) for r in derived.itertuples()}
    if not by_d:
        return 0
    merged = 0
    for i, row in df.iterrows():
        minutes = by_d.get(row["d"])
        if minutes is None:
            continue
        stops = list(row["stops"]) if isinstance(row["stops"], list) else []
        if not stops or not isinstance(stops[0], dict):
            continue  # need a first stop to attach the wait to
        # Only fill a gap — a wait already logged on the ride always wins.
        if stops[0].get("waiting_duration"):
            continue
        stops[0] = {**stops[0], "waiting_duration": f"PT{minutes}M"}
        df.at[i, "stops"] = stops
        merged += 1
    return merged


_merged_waits = merge_derived_waits(rides_df)
logger.info(f"Merged {_merged_waits} derived wait time(s) from comment text")


def get_vehicle_kind(mot):
    if isinstance(mot, dict):
        return mot.get("kind") or None
    return None


rides_df["vehicle_kind"] = rides_df["mode_of_transportation"].apply(get_vehicle_kind)


logger.info("Extracting start and end coordinates")


def get_start_end_coords(row):
    start_location = row["stops"][0]["location"]

    start_lat = start_location["latitude"]
    start_lon = start_location["longitude"]

    if len(row["stops"]) > 1:
        end_location = row["stops"][-1]["location"]
        dest_lat = end_location["latitude"]
        dest_lon = end_location["longitude"]
    else:
        dest_lat = None
        dest_lon = None

    return pd.Series({"start_lat": start_lat, "start_lon": start_lon, "dest_lat": dest_lat, "dest_lon": dest_lon})


rides_df[["lat", "lon", "dest_lat", "dest_lon"]] = rides_df.apply(get_start_end_coords, axis=1)

# rides_df["user_id"] = rides_df["user_id"].astype(pd.Int64Dtype())

# logger.info("Fetching duplicates from database")
# duplicates = pd.read_sql("select * from duplicates where reviewed = accepted", get_db())

# try:
#     logger.info("Fetching users from database")
#     users = pd.read_sql("select * from user", get_db())
# except pd.errors.DatabaseError as err:
#     logger.error("Failed to fetch users from database")
#     raise Exception("Run server.py to create the user table") from err

# merging and transforming data
# dup_rads = duplicates[["from_lon", "from_lat", "to_lon", "to_lat"]].values.T

# duplicates["distance"] = haversine_np(*dup_rads)
# duplicates["from"] = duplicates[["from_lat", "from_lon"]].apply(tuple, axis=1)
# duplicates["to"] = duplicates[["to_lat", "to_lon"]].apply(tuple, axis=1)

# duplicates = duplicates[duplicates.distance < 1.25]

# dups = networkx.from_pandas_edgelist(duplicates, "from", "to")
# islands = networkx.connected_components(dups)

# replace_map = {}

# logger.info("Processing duplicates")
# for island in islands:
#     parents = [node for node in island if node not in duplicates["from"].tolist()]

#     if len(parents) == 1:
#         for node in island:
#             if node != parents[0]:
#                 replace_map[node] = parents[0]

# logger.info(f"Currently recorded duplicate spots are represented by: ${dups}")

# logger.info("Replacing duplicate rides_df")
# rides_df[["lat", "lon"]] = rides_df[["lat", "lon"]].apply(lambda x: replace_map.get(tuple(x), x), axis=1, raw=True)

# rides_df.loc[rides_df.id.isin(range(1000000, 1040000)), "comment"] = (
#     rides_df.loc[rides_df.id.isin(range(1000000, 1040000)), "comment"]
#     .str.encode("cp1252", errors="ignore")
#     .str.decode("utf-8", errors="ignore")
# )

rides_df["submission_time"] = pd.to_datetime(rides_df["submission_time"])


def get_ride_datetime(row):
    start_location = row["stops"][0]
    ride_datetime = start_location.get("departure_time", None)

    return ride_datetime


def get_arrival_datetime(row):
    stops = row["stops"]
    if not stops or len(stops) < 2:
        return None
    return stops[-1].get("arrival_time", None)


rides_df["ride_datetime"] = rides_df.apply(get_ride_datetime, axis=1)
rides_df["ride_datetime"] = pd.to_datetime(rides_df["ride_datetime"], errors="coerce")
rides_df["arrival_datetime"] = rides_df.apply(get_arrival_datetime, axis=1)
rides_df["arrival_datetime"] = pd.to_datetime(rides_df["arrival_datetime"], errors="coerce")

rads = rides_df[["lat", "lon", "dest_lat", "dest_lon"]].values.T

logger.info("Calculating distances and directions")
rides_df["distance"] = haversine_np(*rads)
rides_df["direction"] = get_bearing(*rads)

logger.info("Cleaning where ride distance is unrealisticly short")
rides_df.loc[(rides_df.distance < 1), "dest_lat"] = None
rides_df.loc[(rides_df.distance < 1), "dest_lon"] = None
rides_df.loc[(rides_df.distance < 1), "direction"] = None
rides_df.loc[(rides_df.distance < 1), "distance"] = None

rounded_dir = 45 * np.round(rides_df.direction / 45)
rides_df["arrows"] = rounded_dir.replace(
    {
        -90: "←",
        90: "→",
        0: "↑",
        180: "↓",
        -180: "↓",
        -45: "↖",
        45: "↗",
        135: "↘",
        -135: "↙",
    }
)

logger.info("Generating texts")
rating_text = "rating: " + rides_df["rating"].astype(str) + "/5"
destination_text = (
    ", ride: " + np.round(rides_df["distance"]).astype(str).str.replace(".0", "", regex=False) + " km " + rides_df["arrows"]
)


logger.info("Calculating wait times")


def get_wait(row):
    start_location = row["stops"][0]
    wait = start_location.get("waiting_duration", None)

    if wait is not None:
        # Convert ISO 8601 duration to minutes
        # TODO: first verify that it is proper iso format
        wait = int(wait.replace("PT", "").replace("M", ""))

    return wait


rides_df["wait"] = rides_df.apply(get_wait, axis=1)


logger.info("Determining signals")


def get_signals(approaches):
    if approaches is None or not isinstance(approaches, list):
        return None  # No signals available

    signals = []

    for approach in approaches:
        signals.extend(approach.get("methods", []))

    symbol_map = {"asking": "💬", "sign": "🪧", "thumb": "👍"}
    symbols = ",".join(symbol_map.get(sig, sig) for sig in set(signals))

    return symbols


def get_signal_methods(approaches):
    """Return the unique list of signal methods used on a ride (or None)."""
    if approaches is None or not isinstance(approaches, list):
        return None
    seen = []
    for approach in approaches:
        for m in approach.get("methods", []) or []:
            if m and m not in seen:
                seen.append(m)
    return seen or None


rides_df["signal"] = rides_df["signals"].apply(get_signals)
rides_df["signal_methods"] = rides_df["signals"].apply(get_signal_methods)

logger.info("Generating info texts")
rides_df["wait_text"] = None
has_accurate_wait = ~rides_df["wait"].isnull() & rides_df["source"] != "liftershalte.info"
rides_df.loc[has_accurate_wait, "wait_text"] = (
    ", wait: "
    + rides_df["wait"][has_accurate_wait].astype(str)
    + " min"
    + (" " + rides_df["signal"][has_accurate_wait]).fillna("")
)

rides_df["extra_text"] = rating_text + rides_df.wait_text.fillna("") + destination_text.fillna("")

comment_nl = rides_df["comment"] + "\n\n"

comment_nl.loc[(rides_df["submission_time"].dt.year > 2021) & rides_df.comment.isnull()] = ""

review_submit_datetime = rides_df["submission_time"].dt.strftime(", %B %Y").fillna("")

# rides_df["username"] = pd.merge(
#     left=rides_df[["user_id"]],
#     right=users[["id", "username"]],
#     left_on="user_id",
#     right_on="id",
#     how="left",
# )["username"]


logger.info("Generating user links")


def get_hitchhiker_name(hitchhikers):
    if isinstance(hitchhikers, list) and len(hitchhikers) > 0:
        first_hitchhiker = hitchhikers[0]
        if (
            isinstance(first_hitchhiker, dict)
            and "nickname" in first_hitchhiker
            and first_hitchhiker["nickname"].strip() != ""
            and pd.notna(first_hitchhiker["nickname"])
        ):
            return first_hitchhiker["nickname"]
    return "Anonymous"


rides_df["hitchhiker_name"] = rides_df["hitchhikers"].apply(get_hitchhiker_name)

# A ride is "low-value" when it is anonymous and carries no information beyond a
# bare rating: no written comment and no recorded waiting time. These (mostly
# legacy single-rating imports, e.g. 51.6816, 9.1609) clutter the map, so we drop
# them from every detail view and remove spots made up entirely of them — while
# still counting them toward a surviving spot's review_count (see
# total_ride_counts below, computed before the rides are filtered out).
comment_blank = rides_df["comment"].fillna("").astype(str).str.strip() == ""
rides_df["is_informative"] = ~((rides_df["hitchhiker_name"] == "Anonymous") & comment_blank & rides_df["wait"].isnull())


logger.info("Computing per-user lifetime stats and updating the user table")

# Aggregate lifetime stats per hitchhiker so the profile "Insights" section can
# render them without re-aggregating every ride on each page load. "Anonymous"
# is the sentinel for rides with no nickname, so it's excluded from user stats.
# distance/wait carry NaN for rides without a destination / waiting time;
# pandas sum skips those (skipna=True) and yields 0 when a user has none.
named_rides = rides_df[rides_df["hitchhiker_name"] != "Anonymous"]
user_stats = named_rides.groupby("hitchhiker_name").agg(
    total_rides=("hitchhiker_name", "size"),
    total_distance_km=("distance", "sum"),
    total_waiting_time_min=("wait", "sum"),
)

# This runs before any JSON file is written, so the DB write below stays older
# than the generated files and won't make should_regenerate_json() loop forever.
stats_conn = get_db()
# No migration framework: ensure the columns exist so a fresh deploy doesn't 500
# on the first profile load. Idempotent — a re-add raises OperationalError.
for col, coltype in (("total_rides", "INTEGER"), ("total_distance_km", "REAL"), ("total_waiting_time_min", "INTEGER")):
    # Idempotent re-add raises OperationalError when the column already exists.
    with contextlib.suppress(sqlite3.OperationalError):
        stats_conn.execute(f"ALTER TABLE user ADD COLUMN {col} {coltype}")

# Match nicknames to usernames case-insensitively (consistent with the leaderboard);
# only registered users have a row to update — unregistered nicknames are ignored.
stat_updates = [
    (
        int(row.total_rides),
        round(float(row.total_distance_km), 1) if pd.notna(row.total_distance_km) else 0,
        int(row.total_waiting_time_min) if pd.notna(row.total_waiting_time_min) else 0,
        name.lower(),
    )
    for name, row in user_stats.iterrows()
]
# Zero everyone first, then re-apply the surviving totals. A user who hid/removed
# ALL their rides drops out of user_stats entirely, so a plain per-nickname UPDATE
# would never touch their row and their cached totals would freeze at the last
# non-zero value (their profile then shows "0 rides" from the live query but stale
# rides/km/min in Insights and achievements). The reset + re-apply run in one
# transaction, so no user ever observes a transient zero.
stats_conn.execute("UPDATE user SET total_rides = 0, total_distance_km = 0, total_waiting_time_min = 0")
stats_conn.executemany(
    "UPDATE user SET total_rides = ?, total_distance_km = ?, total_waiting_time_min = ? WHERE lower(username) = ?",
    stat_updates,
)
stats_conn.commit()
logger.info(f"Applied user stats for {len(stat_updates)} distinct nicknames")

rides_df["user_link"] = (
    "<a href='/account/" + e(rides_df["hitchhiker_name"]) + "'>" + e(rides_df["hitchhiker_name"]) + "</a>"
).fillna(
    "Anonymous  "
    + '<i class="icon-button fa fa-hand" title="Claim this review as yours." onclick="confirmClaimReview(\'/claim-review/'
    + rides_df["id"].astype(str)
    + "')\"></i>"
)

rides_df["text"] = (
    e(comment_nl)
    + "<i>"
    + e(rides_df["extra_text"])
    + "</i><br><br>―"
    + rides_df["user_link"]
    + rides_df.ride_datetime.dt.strftime(", %a %d %b %Y, %H:%M").fillna(review_submit_datetime)
)

oldies = rides_df["submission_time"].dt.year <= 2021
rides_df.loc[oldies, "text"] = (
    e(comment_nl[oldies])
    + "―"
    + rides_df.loc[oldies, "user_link"]
    + rides_df[oldies]["submission_time"].dt.strftime(", %B %Y").fillna("")
)

# Spots submitted within a few metres of each other are almost always the same
# physical hitchhiking spot — GPS jitter or a slightly different pin drop. Merge
# them so the map shows one marker whose popup aggregates all their rides instead
# of a cluster of near-identical pins. DBSCAN with min_samples=1 gives
# single-linkage "chaining": if A is within MERGE_RADIUS_M of B and B of C, then
# A, B and C collapse into one spot even when A and C are further apart. This is
# the modern, automatic replacement for the manual duplicate-merging above.
MERGE_RADIUS_M = 5
EARTH_RADIUS_M = 6_371_000

unique_coords = rides_df[["lat", "lon"]].drop_duplicates().reset_index(drop=True)
if len(unique_coords) > 1:
    logger.info(f"Clustering {len(unique_coords)} distinct coordinates within {MERGE_RADIUS_M} m")
    # haversine expects radians and returns the great-circle distance in radians,
    # so eps is the merge radius expressed as an arc length on the unit sphere.
    unique_coords["cluster"] = DBSCAN(
        eps=MERGE_RADIUS_M / EARTH_RADIUS_M,
        min_samples=1,
        metric="haversine",
        algorithm="ball_tree",
    ).fit_predict(np.radians(unique_coords[["lat", "lon"]].values))

    # Anchor each cluster on its busiest member coordinate (most rides, ties
    # broken by lat then lon). Using a real submitted point keeps the spot id /
    # URL stable as new rides arrive, instead of drifting like a centroid would.
    ride_counts = rides_df.groupby(["lat", "lon"]).size().rename("n")
    unique_coords = unique_coords.merge(ride_counts, on=["lat", "lon"], how="left")
    unique_coords.sort_values(["cluster", "n", "lat", "lon"], ascending=[True, False, True, True], inplace=True)
    anchors = unique_coords.groupby("cluster")[["lat", "lon"]].first()
    anchors.columns = ["anchor_lat", "anchor_lon"]
    unique_coords = unique_coords.merge(anchors, on="cluster", how="left")

    logger.info(f"Merged {len(unique_coords) - int(unique_coords['cluster'].nunique())} coordinates into nearby spots")

    # Remap every ride to its cluster anchor via a dict (preserves rides_df's
    # index, unlike a merge). Everything downstream — the groupby, spot-id
    # generation, per-spot ride counts — keys off lat/lon, so swapping the
    # coordinates here merges the spots across all generated files with no other
    # change.
    anchor_lat = dict(zip(zip(unique_coords["lat"], unique_coords["lon"]), unique_coords["anchor_lat"]))
    anchor_lon = dict(zip(zip(unique_coords["lat"], unique_coords["lon"]), unique_coords["anchor_lon"]))
    keys = list(zip(rides_df["lat"], rides_df["lon"]))
    rides_df["lat"] = [anchor_lat[k] for k in keys]
    rides_df["lon"] = [anchor_lon[k] for k in keys]

# Coarser grouping on top of the 5 m merge: spots inside the same OSM service area
# (gas station / rest stop) or the same road island are the same physical hitchhiking
# spot even when tens of metres apart, so people's scattered pins around one filling
# station or junction should collapse to one marker. The polygons come from
# sync_service_areas / sync_road_islands; we assign each coordinate the polygon that
# contains it (service area wins over road island, matching hitchmap's precedence) and
# remap every ride to a single busiest-member anchor per polygon — exactly the anchor
# trick the 5 m merge uses, so the spot id / per-spot files stay stable.
t_group = time.perf_counter()

# Names of the service-area polygons, keyed by the anchor coordinate of the spot they
# swallowed. Populated below; feeds the spot's display name, so the name a spot shows
# always describes the polygon it was actually merged into.
service_area_name_by_anchor = {}
try:
    service_areas_df = pd.read_sql("select geom_id, name, geometry_wkt from service_area", get_db())
    road_islands_df = pd.read_sql("select id, geometry_wkt from road_island", get_db())
except (pd.errors.DatabaseError, sqlite3.OperationalError):
    # Tables absent (sync scripts never run, e.g. fresh/dev DB): keep the 5 m merge only.
    logger.info("service_area / road_island tables not found — skipping polygon grouping")
    service_areas_df = road_islands_df = None

if service_areas_df is not None and (len(service_areas_df) or len(road_islands_df)):
    logger.info(f"Polygon grouping: {len(service_areas_df)} service areas, {len(road_islands_df)} road islands")
    unique_pts = rides_df[["lat", "lon"]].drop_duplicates().reset_index(drop=True)
    lat_list = unique_pts["lat"].tolist()
    lon_list = unique_pts["lon"].tolist()
    # Polygons were built in (lon, lat) order, so query points must match.
    points = [Point(lon, lat) for lat, lon in zip(lat_list, lon_list)]

    def assign_polygon(geoms, ids):
        """For each unique point, return the id of the containing polygon (largest if
        several contain it) or None. An STRtree bbox prefilter keeps the no-match case —
        the vast majority of spots — cheap."""
        if not geoms:
            return [None] * len(points)
        tree = STRtree(geoms)
        polygon_areas = [g.area for g in geoms]
        assigned = []
        for pt in points:
            # STRtree tests query_geom.predicate(tree_geom); "within" → this point lies
            # inside the tree polygon. (predicate="contains" would test point.contains(poly).)
            candidates = tree.query(pt, predicate="within")
            if len(candidates) == 0:
                assigned.append(None)
            else:
                assigned.append(ids[max(candidates, key=lambda idx: polygon_areas[idx])])
        return assigned

    sa_geoms = [wkt_loads(w) for w in service_areas_df["geometry_wkt"]]
    ri_geoms = [wkt_loads(w) for w in road_islands_df["geometry_wkt"]]
    sa_ids = assign_polygon(sa_geoms, service_areas_df["geom_id"].tolist())
    ri_ids = assign_polygon(ri_geoms, road_islands_df["id"].tolist())

    # One grouping label per coordinate; service area takes precedence over road island,
    # and points in neither keep their own coordinate (i.e. the 5 m-merge result). Build
    # the labels as plain strings from Python lists — assigning a None/int list into a
    # DataFrame column would coerce None to NaN (float), and `NaN is not None` is True, so
    # every unmatched point would be mislabelled and collapse into one giant spot.
    labels = []
    for sa_id, ri_id, lat, lon in zip(sa_ids, ri_ids, lat_list, lon_list):
        if sa_id is not None:
            labels.append(f"sa:{sa_id}")
        elif ri_id is not None:
            labels.append(f"ri:{ri_id}")
        else:
            labels.append(f"pt:{lat}:{lon}")
    unique_pts["label"] = labels

    # Anchor each label on its busiest member coordinate (most rides, ties by lat/lon) so
    # the chosen spot coordinate is a real submitted point and stays put as rides change.
    ride_counts = rides_df.groupby(["lat", "lon"]).size().rename("n").reset_index()
    unique_pts = unique_pts.merge(ride_counts, on=["lat", "lon"], how="left")
    unique_pts.sort_values(["n", "lat", "lon"], ascending=[False, True, True], inplace=True)
    anchors = unique_pts.groupby("label", sort=False)[["lat", "lon"]].first()
    anchors.columns = ["anchor_lat", "anchor_lon"]
    unique_pts = unique_pts.merge(anchors, on="label", how="left")

    # Carry each service area's name onto the anchor it produced, so the spot can be
    # titled after the rest area / filling station it sits in. Read from the same label
    # the merge used, never re-derived, or the name could describe a different polygon
    # than the one the spot was folded into.
    sa_name_by_id = dict(zip(service_areas_df["geom_id"], service_areas_df["name"]))
    for label, a_lat, a_lon in zip(unique_pts["label"], unique_pts["anchor_lat"], unique_pts["anchor_lon"]):
        if label.startswith("sa:"):
            service_area_name_by_anchor[(a_lat, a_lon)] = sa_name_by_id.get(int(label[3:]))

    anchor_lat = dict(zip(zip(unique_pts["lat"], unique_pts["lon"]), unique_pts["anchor_lat"]))
    anchor_lon = dict(zip(zip(unique_pts["lat"], unique_pts["lon"]), unique_pts["anchor_lon"]))
    keys = list(zip(rides_df["lat"], rides_df["lon"]))
    rides_df["lat"] = [anchor_lat[k] for k in keys]
    rides_df["lon"] = [anchor_lon[k] for k in keys]

    # Distinct polygons that actually captured ≥1 coordinate (not the per-coordinate "pt:" labels).
    n_polygon_spots = len({lbl for lbl in labels if not lbl.startswith("pt:")})
    logger.info(
        f"Polygon grouping merged coords into {n_polygon_spots} service-area/road-island "
        f"spots in {time.perf_counter() - t_group:.1f}s"
    )

# Count every ride per (anchored) spot BEFORE dropping the low-value ones, so a
# surviving spot's review_count still reflects the anonymous rating-only rides we
# remove below. Keyed by the (lat, lon) tuple to match `place` rows further down.
total_ride_counts = rides_df.groupby(["lat", "lon"]).size().to_dict()

# Drop anonymous, information-free rides from everything downstream (places
# aggregation, per-spot detail files, rides_index, recent). Spots left with no
# informative ride simply won't appear in `places` below, removing them from the
# map; their full ride tally is preserved in total_ride_counts for spots that
# keep at least one informative ride.
rides_df = rides_df[rides_df["is_informative"]].copy()

groups = rides_df.groupby(["lat", "lon"])

places = groups[["source"]].first()  # TODO: this is a trick for now
places["rating"] = groups.rating.mean().round(1)
places["wait"] = rides_df[~rides_df.wait.isnull()].groupby(["lat", "lon"]).wait.mean()
places["distance"] = rides_df[~rides_df.distance.isnull()].groupby(["lat", "lon"]).distance.mean()
places["text"] = groups.text.apply(lambda t: "<hr>".join(t.dropna()))

places["dest_lats"] = rides_df.dropna(subset=["dest_lat", "dest_lon"]).groupby(["lat", "lon"]).dest_lat.apply(list)
places["dest_lons"] = rides_df.dropna(subset=["dest_lat", "dest_lon"]).groupby(["lat", "lon"]).dest_lon.apply(list)

# Latest submission time per spot (ISO string) for "recent" filtering
places["latest_submission"] = rides_df.dropna(subset=["submission_time"]).groupby(["lat", "lon"])["submission_time"].max()

places.reset_index(inplace=True)
places.sort_values("rating", inplace=True, ascending=False)


def generate_spot_id(lat, lon):
    """Generate coordinate-based spot ID.

    spots.json no longer carries an explicit `id`; the frontend derives it from
    the served lat/lon via `lat.toFixed(5)_lon.toFixed(5)`. We use 5 decimals
    (~1.1 m) — the same precision the coords are served at, and finer than the 5 m
    spot-merge radius — so two anchors the clustering kept apart never collapse to
    the same id. Rounding here matches exactly what the frontend computes, so the
    per-spot filenames `rides/by-spot/<id>.json` line up and the lazy fetch doesn't
    404."""
    return f"{round_coord(lat):.5f}_{round_coord(lon):.5f}"


def round_coord(value):
    """Round a coordinate to 5 decimals (~1 m) for JSON output, to keep the
    served files small. Only applied at serialization time — grouping and spot
    IDs still use the full-precision values."""
    return round(float(value), 5)


logger.info("Fetching OSM hitchhiking spots")
osm_spots_df = pd.read_sql("select id, latitude, longitude from osm_hitchhiking_spot", get_db())

logger.info("Fetching OSM car pooling spots")
car_pooling_df = pd.read_sql("select id, osm_type, latitude, longitude from osm_car_pooling_spot", get_db())

logger.info("Fetching OSM fuel stations")
fuel_df = pd.read_sql("select id, osm_type, latitude, longitude from osm_fuel_station_spot", get_db())


def build_fuel_grid(df):
    """Bucket fuel stations into a ~1.1 km grid (0.01°-rounded lat/lon cells).

    Fuel stations are a far larger set than car-pooling / official spots (hundreds
    of thousands globally). A full haversine scan per place (~45k places) would be
    tens of billions of ops, so instead a 100 m lookup only checks the 3x3
    neighbouring cells (each cell is ~1.1 km, well over the 100 m radius)."""
    grid = {}
    if df.empty:
        return grid
    for row in df.itertuples(index=False):
        key = (round(row.latitude, 2), round(row.longitude, 2))
        grid.setdefault(key, []).append((int(row.id), row.osm_type, row.latitude, row.longitude))
    return grid


fuel_grid = build_fuel_grid(fuel_df)
logger.info(f"Built fuel-station grid: {len(fuel_df)} stations in {len(fuel_grid)} cells")


def find_nearby_fuel_station(lat, lon, grid, max_distance_km=0.1) -> dict | None:
    """Find the nearest OSM fuel station within max_distance_km (default 100m).

    Returns {"id": int, "osm_type": str} or None — both are needed to build a stable
    OSM URL, since fuel is often mapped on ways/relations rather than nodes. Uses the
    spatial grid from build_fuel_grid so only nearby cells are scanned."""
    if not grid:
        return None
    clat, clon = round(lat, 2), round(lon, 2)
    best = None
    best_dist = None
    for dlat in (-0.01, 0.0, 0.01):
        for dlon in (-0.01, 0.0, 0.01):
            cell = grid.get((round(clat + dlat, 2), round(clon + dlon, 2)))
            if not cell:
                continue
            for fid, ftype, flat, flon in cell:
                # Same haversine (with the 1.25 road factor) used by the other
                # nearby-spot checks, kept scalar since each cell holds few stations.
                dist = float(haversine_np(lat, lon, flat, flon))
                if dist <= max_distance_km and (best_dist is None or dist < best_dist):
                    best_dist = dist
                    best = {"id": fid, "osm_type": ftype}
    return best


def find_nearby_osm_spot(lat, lon, osm_spots, max_distance_km=0.1) -> int | None:
    """Find the nearest OSM hitchhiking spot within max_distance_km (default 100m)."""
    if osm_spots.empty:
        return None

    # Calculate distances using haversine formula
    distances = haversine_np(
        lat1=np.array([lat] * len(osm_spots)),
        lon1=np.array([lon] * len(osm_spots)),
        lat2=osm_spots["latitude"].values,
        lon2=osm_spots["longitude"].values,
    )

    # Find spots within the maximum distance
    nearby_mask = distances <= max_distance_km
    if not nearby_mask.any():
        return None

    # Return the ID of the closest spot
    nearby_spots = osm_spots[nearby_mask]
    nearby_distances = distances[nearby_mask]
    closest_idx = nearby_distances.argmin()
    return nearby_spots.iloc[closest_idx]["id"]


def find_nearby_car_pooling_spot(lat, lon, car_pooling_spots, max_distance_km=0.1) -> dict | None:
    """Find the nearest OSM car pooling spot within max_distance_km (default 100m).

    Returns {"id": int, "osm_type": str} or None — both are needed to build a stable OSM URL,
    since car_pooling is often tagged on ways/relations rather than nodes.
    """
    if car_pooling_spots.empty:
        return None

    distances = haversine_np(
        lat1=np.array([lat] * len(car_pooling_spots)),
        lon1=np.array([lon] * len(car_pooling_spots)),
        lat2=car_pooling_spots["latitude"].values,
        lon2=car_pooling_spots["longitude"].values,
    )

    nearby_mask = distances <= max_distance_km
    if not nearby_mask.any():
        return None

    nearby = car_pooling_spots[nearby_mask]
    nearby_distances = distances[nearby_mask]
    closest_idx = nearby_distances.argmin()
    row = nearby.iloc[closest_idx]
    return {"id": int(row["id"]), "osm_type": row["osm_type"]}


hitchwiki_df = pd.read_sql(
    "select id, title, heading, latitude, longitude, hitchwiki_url from hitchwiki_article_location", get_db()
)

logger.info("Loading Hitchwiki map data")
hitchwiki_maps_df = pd.read_sql("select id, title, latitude, longitude, zoom, hitchwiki_url from hitchwiki_article_map", get_db())


def find_nearby_hitchwiki_article(lat, lon, hitchwiki_articles, max_distance_km=0.1) -> str | None:
    """Find the nearest Hitchwiki article location within max_distance_km (default 100m)."""
    if hitchwiki_articles.empty:
        return None

    distances = haversine_np(
        lat1=np.array([lat] * len(hitchwiki_articles)),
        lon1=np.array([lon] * len(hitchwiki_articles)),
        lat2=hitchwiki_articles["latitude"].values,
        lon2=hitchwiki_articles["longitude"].values,
    )

    nearby_mask = distances <= max_distance_km
    if not nearby_mask.any():
        return None

    # Return the link of the closest article
    nearby_articles = hitchwiki_articles[nearby_mask]
    nearby_distances = distances[nearby_mask]
    closest_idx = nearby_distances.argmin()
    return nearby_articles.iloc[closest_idx]["hitchwiki_url"]


def get_map_bounds(center_lat, center_lng, zoom=11, map_width=300, map_height=300):
    scale = 2**zoom
    world_width = 256 * scale

    # Convert center to world coordinates
    center_x = (center_lng + 180) * world_width / 360
    center_y = world_width / 2 - math.log(math.tan((center_lat + 90) * math.pi / 360)) * world_width / (2 * math.pi)

    # Calculate bounds in world coordinates
    half_width = map_width / 2
    half_height = map_height / 2

    west_x = center_x - half_width
    east_x = center_x + half_width
    north_y = center_y - half_height
    south_y = center_y + half_height

    # Convert back to lat/lng
    west = (west_x * 360 / world_width) - 180
    east = (east_x * 360 / world_width) - 180
    north = (math.atan(math.exp((world_width / 2 - north_y) * 2 * math.pi / world_width)) * 360 / math.pi) - 90
    south = (math.atan(math.exp((world_width / 2 - south_y) * 2 * math.pi / world_width)) * 360 / math.pi) - 90

    return {"north": north, "south": south, "east": east, "west": west}


def find_hitchwiki_map_for_spot(lat, lon, hitchwiki_maps, map_width=300, map_height=300) -> str | None:
    """Find the Hitchwiki article map with highest zoom where the spot is visible."""
    # TODO: too slow in dev mode
    return None
    if hitchwiki_maps.empty:
        return None

    visible_maps = []

    for _, map_row in hitchwiki_maps.iterrows():
        bounds = get_map_bounds(
            center_lat=map_row["latitude"],
            center_lng=map_row["longitude"],
            zoom=map_row["zoom"],
            map_width=map_width,
            map_height=map_height,
        )

        # Check if spot is within map bounds
        if bounds["south"] <= lat <= bounds["north"] and bounds["west"] <= lon <= bounds["east"]:
            visible_maps.append({"zoom": map_row["zoom"], "url": map_row["hitchwiki_url"]})

    if not visible_maps:
        return None

    # Return the URL of the map with the highest zoom level
    highest_zoom_map = max(visible_maps, key=lambda x: x["zoom"])
    return highest_zoom_map["url"]


logger.info("Finding nearby OSM spots")
places["nearby_osm_id"] = places.apply(lambda row: find_nearby_osm_spot(row["lat"], row["lon"], osm_spots_df), axis=1)
logger.info(f"Found {places['nearby_osm_id'].notnull().sum()} places with nearby OSM spots")

logger.info("Finding nearby OSM car pooling spots")
places["nearby_car_pooling"] = places.apply(
    lambda row: find_nearby_car_pooling_spot(row["lat"], row["lon"], car_pooling_df), axis=1
)
logger.info(f"Found {places['nearby_car_pooling'].notnull().sum()} places with nearby car pooling spots")

logger.info("Finding nearby OSM fuel stations")
places["nearby_fuel"] = places.apply(lambda row: find_nearby_fuel_station(row["lat"], row["lon"], fuel_grid), axis=1)
logger.info(f"Found {places['nearby_fuel'].notnull().sum()} places at a fuel station")

logger.info("Finding nearby Hitchwiki articles")
places["nearby_hitchwiki_link"] = places.apply(
    lambda row: find_nearby_hitchwiki_article(row["lat"], row["lon"], hitchwiki_df), axis=1
)
logger.info(f"Found {places['nearby_hitchwiki_link'].notnull().sum()} places with nearby Hitchwiki articles")

logger.info("Finding Hitchwiki maps covering spots")
places["hitchwiki_map_link"] = places.apply(
    lambda row: find_hitchwiki_map_for_spot(row["lat"], row["lon"], hitchwiki_maps_df), axis=1
)
logger.info(f"Found {places['hitchwiki_map_link'].notnull().sum()} places visible in Hitchwiki maps")


def fetch_osm_tags(table, ids):
    """{osm_id: tags} for just the features that matched a spot.

    Deliberately NOT part of the bulk reads above: `tags` is a JSON blob, and pulling it
    for all 406k fuel stations costs roughly 200 MB resident on a host the OOM killer has
    already visited (CLAUDE.md). Only ~5.5k of them are ever within 100 m of a spot.
    """
    ids = sorted({int(i) for i in ids if pd.notna(i)})
    if not ids:
        return {}
    tags = {}
    # SQLite allows 999 bound variables per statement by default; chunk under that.
    for start in range(0, len(ids), 900):
        chunk = ids[start : start + 900]
        placeholders = ",".join("?" * len(chunk))
        rows = pd.read_sql(f"select id, tags from {table} where id in ({placeholders})", get_db(), params=chunk)
        for _, row in rows.iterrows():
            value = row["tags"]
            with contextlib.suppress(ValueError, TypeError):
                tags[int(row["id"])] = json.loads(value) if isinstance(value, str) else value
    return tags


logger.info("Fetching OSM tags for matched features")
osm_spot_tags = fetch_osm_tags("osm_hitchhiking_spot", places["nearby_osm_id"])
fuel_tags = fetch_osm_tags("osm_fuel_station_spot", [f["id"] for f in places["nearby_fuel"] if f])
car_pooling_tags = fetch_osm_tags("osm_car_pooling_spot", [c["id"] for c in places["nearby_car_pooling"] if c])

# Reverse-geocoded street names for the ~84% of spots no OSM feature can name, cached by
# hitch/scripts/spot_names.py. Absent on a fresh/dev DB that has never run it.
try:
    spot_names_df = pd.read_sql("select spot_id, name from spot_name", get_db())
    geocoded_names = dict(zip(spot_names_df["spot_id"], spot_names_df["name"]))
except (pd.errors.DatabaseError, sqlite3.OperationalError):
    logger.info("spot_name table not found — spots with no OSM feature will stay unnamed")
    geocoded_names = {}
logger.info(f"Loaded {len(geocoded_names)} cached geocoded spot names")

logger.info("Generating JSON data files")

# spots.json is downloaded by every visitor on map load, so it only carries
# what the frontend needs to draw and filter the markers. Click-time detail
# (wait/distance averages, OSM / car-pooling / Hitchwiki links) goes into the
# lazy per-spot files instead — collected here into spot_details.
spots_data = []
spot_details = {}
for _, place in places.iterrows():
    spot_id = generate_spot_id(place["lat"], place["lon"])
    # No explicit "id": it's redundant with lat/lon. The frontend re-derives the
    # spot id (used to fetch rides/by-spot/<id>.json) from these rounded coords.
    spot_data = {
        "lat": round_coord(place["lat"]),
        "lon": round_coord(place["lon"]),
        "rating": place["rating"],
        # Total number of ride entries logged at this spot, including the dropped
        # anonymous rating-only rides (see total_ride_counts). Drives the marker
        # stroke weight / bring-to-front and the "minimum rides" frontend filter.
        "review_count": int(total_ride_counts.get((place["lat"], place["lon"]), 0)),
    }
    # Epoch ms instead of an ISO string: smaller and directly comparable to Date.now()
    # in the recent-rides filter. Omitted (like all sparse fields below) when absent.
    if pd.notna(place["latest_submission"]):
        spot_data["latest_ms"] = int(place["latest_submission"].timestamp() * 1000)
    # Destination coords are needed at load time for the direction filter and the
    # destination lines drawn for a selected spot.
    if isinstance(place["dest_lats"], list) and len(place["dest_lats"]):
        spot_data["dest_lats"] = [round_coord(v) for v in place["dest_lats"]]
        spot_data["dest_lons"] = [round_coord(v) for v in place["dest_lons"]]
    # The spot filters only check presence of these, so ship booleans; the actual
    # ids/links are in the per-spot detail. Only a few hundred of ~45k spots have
    # any of them, hence flags are omitted instead of written as false.
    if pd.notna(place["nearby_osm_id"]):
        spot_data["osm"] = True
    if place["nearby_car_pooling"] is not None:
        spot_data["cp"] = True
    if place["nearby_fuel"] is not None:
        spot_data["fuel"] = True
    if place["nearby_hitchwiki_link"] is not None:
        spot_data["wiki"] = True
    if place["hitchwiki_map_link"] is not None:
        spot_data["wikimap"] = True
    spots_data.append(spot_data)

    detail = {}
    # Human-readable title for the spot pane, in place of bare coordinates. Lives in the
    # per-spot file rather than spots.json: ~30k name strings would add roughly a
    # megabyte to the file every visitor downloads on map load, and nothing needs the
    # name before a marker is clicked.
    name = resolve_spot_name(
        hitchhiking_tags=osm_spot_tags.get(int(place["nearby_osm_id"])) if pd.notna(place["nearby_osm_id"]) else None,
        service_area_name=service_area_name_by_anchor.get((place["lat"], place["lon"])),
        fuel_tags=fuel_tags.get(place["nearby_fuel"]["id"]) if place["nearby_fuel"] else None,
        car_pooling_tags=car_pooling_tags.get(place["nearby_car_pooling"]["id"]) if place["nearby_car_pooling"] else None,
        geocoded_name=geocoded_names.get(spot_id),
    )
    if name:
        detail["name"] = name
    # The popup only ever shows these as whole numbers (toFixed(0)), so store
    # them rounded to ints — smaller payload, no precision the UI would use.
    if pd.notna(place["wait"]):
        detail["wait"] = round(float(place["wait"]))
    if pd.notna(place["distance"]):
        detail["distance"] = round(float(place["distance"]))
    if pd.notna(place["nearby_osm_id"]):
        # int(): the column is float64 because it holds NaN, and a trailing ".0"
        # would break the openstreetmap.org/node/<id> URL built in the frontend.
        detail["osm_id"] = int(place["nearby_osm_id"])
    if place["nearby_car_pooling"] is not None:
        detail["car_pooling"] = place["nearby_car_pooling"]
    if place["nearby_fuel"] is not None:
        detail["fuel"] = place["nearby_fuel"]
    if place["nearby_hitchwiki_link"] is not None:
        detail["hitchwiki_article"] = place["nearby_hitchwiki_link"]
    if place["hitchwiki_map_link"] is not None:
        detail["hitchwiki_map"] = place["hitchwiki_map_link"]
    spot_details[spot_id] = detail

write_json_file(spots_data, "spots.json")

# Generate individual rides data
rides_data = []
for _, ride in rides_df.iterrows():
    # Handle submission_time - check if it's already a datetime or string
    submission_time = None
    if pd.notna(ride["submission_time"]):
        if hasattr(ride["submission_time"], "isoformat"):
            submission_time = ride["submission_time"].isoformat()
        else:
            submission_time = str(ride["submission_time"])

    # Handle ride_datetime similarly
    ride_datetime = None
    if pd.notna(ride.get("ride_datetime")):
        if hasattr(ride["ride_datetime"], "isoformat"):
            ride_datetime = ride["ride_datetime"].isoformat()
        else:
            ride_datetime = str(ride["ride_datetime"])

    arrival_datetime = None
    if pd.notna(ride.get("arrival_datetime")):
        if hasattr(ride["arrival_datetime"], "isoformat"):
            arrival_datetime = ride["arrival_datetime"].isoformat()
        else:
            arrival_datetime = str(ride["arrival_datetime"])

    ride_data = {
        "id": ride["d"] if pd.notna(ride.get("d")) else f"ride_{ride.name}",  # Fallback to index if no d_tag
        "spot_id": generate_spot_id(ride["lat"], ride["lon"]),
        "lat": ride["lat"],
        "lon": ride["lon"],
        "dest_lat": ride["dest_lat"] if pd.notna(ride["dest_lat"]) else None,
        "dest_lon": ride["dest_lon"] if pd.notna(ride["dest_lon"]) else None,
        "rating": int(ride["rating"]) if pd.notna(ride["rating"]) else None,
        "wait": int(ride["wait"]) if pd.notna(ride["wait"]) else None,
        "distance": round(float(ride["distance"]), 1) if pd.notna(ride.get("distance")) else None,
        "comment": ride["comment"] if pd.notna(ride.get("comment")) else None,
        "hitchhiker_name": ride["hitchhiker_name"] if pd.notna(ride.get("hitchhiker_name")) else "Anonymous",
        "submission_time": submission_time,
        "ride_datetime": ride_datetime,
        "arrival_datetime": arrival_datetime,
        "vehicle_kind": ride["vehicle_kind"] if pd.notna(ride.get("vehicle_kind")) else None,
        "signal_methods": ride.get("signal_methods") if isinstance(ride.get("signal_methods"), list) else None,
        "source": ride["source"] if pd.notna(ride.get("source")) else None,
        "no_ride": bool(ride["no_ride"]) if pd.notna(ride.get("no_ride")) else False,
    }
    rides_data.append(ride_data)

# Slim rides index for client-side filtering (filter by user, comment search,
# min distance, last 24h, official spots, hitchwiki). Short keys keep the
# payload small since field names repeat across all rides. Full ride details
# are loaded lazily per-spot when a popup opens.
spot_flags = {
    generate_spot_id(p["lat"], p["lon"]): (
        p["nearby_osm_id"] is not None and pd.notna(p["nearby_osm_id"]),
        p["nearby_hitchwiki_link"] is not None and pd.notna(p["nearby_hitchwiki_link"]),
        p["nearby_car_pooling"] is not None,
        p["nearby_fuel"] is not None,
    )
    for _, p in places.iterrows()
}

COMMENT_EXCERPT_LEN = 200

# Build distance lookup once (avoid O(n²) per-row search inside the loop).
distance_by_d = {
    d: (round(float(dist), 1) if pd.notna(dist) else None) for d, dist in zip(rides_df["d"], rides_df["distance"]) if pd.notna(d)
}

submission_ms = pd.to_datetime(rides_df["submission_time"], errors="coerce", utc=True).astype("int64") // 10**6
ts_by_d = {d: (int(ms) if ms > 0 else None) for d, ms in zip(rides_df["d"], submission_ms) if pd.notna(d)}

ride_dt_ms = pd.to_datetime(rides_df["ride_datetime"], errors="coerce", utc=True).astype("int64") // 10**6
ride_dt_by_d = {d: (int(ms) if ms > 0 else None) for d, ms in zip(rides_df["d"], ride_dt_ms) if pd.notna(d)}

rides_index = []
for r in rides_data:
    sid = r["spot_id"]
    has_osm, has_wiki, has_cp, has_fuel = spot_flags.get(sid, (False, False, False, False))
    comment = r["comment"]

    rides_index.append(
        {
            "id": r["id"],
            "sid": sid,
            "lat": round_coord(r["lat"]),
            "lon": round_coord(r["lon"]),
            "u": r["hitchhiker_name"],
            "t": ts_by_d.get(r["id"]),
            "r": r["rating"],
            "km": distance_by_d.get(r["id"]),
            # Included so the /#insights view can plot a waiting-time histogram from the
            # rides index alone, without fetching every per-spot detail file.
            "w": r["wait"],
            "osm": bool(has_osm),
            "wiki": bool(has_wiki),
            "cp": bool(has_cp),
            "fuel": bool(has_fuel),
            "v": r.get("vehicle_kind"),
            # Unique list of signal methods used on this ride (e.g. ["thumb", "sign"]).
            # Empty/missing → None so the JSON stays small.
            "m": r.get("signal_methods"),
            "rd": ride_dt_by_d.get(r["id"]),
            "c": comment[:COMMENT_EXCERPT_LEN] if comment else None,
        }
    )

write_json_file(rides_index, "rides_index.json")

# Per-spot detail files for lazy popup loading: {"spot": {...}, "rides": [...]}.
# "spot" holds the click-time spot info that was slimmed out of spots.json
# (wait/distance averages, OSM / car-pooling / Hitchwiki links); "rides" holds
# the fields the popup ride cards render. Wipe-and-rewrite ensures spots that
# lost all their rides don't leave stale files behind.
by_spot_dir = os.path.join(dirs["dist"], "rides", "by-spot")
if os.path.exists(by_spot_dir):
    shutil.rmtree(by_spot_dir)
os.makedirs(by_spot_dir, exist_ok=True)


def get_ride_image_urls():
    """Photo URLs per ride d tag, for the spot pane's image strip.

    Only photos already claimed by a ride count — a draft_token row belongs to a form
    nobody has submitted yet. Returns an empty dict if the ride_image table doesn't
    exist (a DB predating the feature), like get_reported_dtags does.
    """
    try:
        images = pd.read_sql(
            "select ride_d_tag, filename from ride_image where ride_d_tag is not null order by id",
            get_db(),
        )
    except pd.errors.DatabaseError:
        return {}
    urls: dict[str, list] = {}
    for d_tag, filename in zip(images["ride_d_tag"], images["filename"]):
        urls.setdefault(d_tag, []).append(image_url(filename))
    return urls


ride_image_urls = get_ride_image_urls()
logger.info(f"Got photos for {len(ride_image_urls)} ride(s)")

logger.info(f"Writing per-spot ride files to {by_spot_dir}")
rides_by_spot: dict[str, list] = {}
for r in rides_data:
    # Omitted entirely for the ~all rides with no photo, rather than shipping an empty
    # list on every entry of every per-spot file.
    images = ride_image_urls.get(r["id"])
    rides_by_spot.setdefault(r["spot_id"], []).append(
        {
            "id": r["id"],
            **({"images": images} if images else {}),
            "rating": r["rating"],
            "wait": r["wait"],
            # Per-ride distance (not just the spot average) so the spot pane can plot a
            # distance histogram without pulling the multi-MB rides index.
            "distance": r["distance"],
            "comment": r["comment"],
            "hitchhiker_name": r["hitchhiker_name"],
            "submission_time": r["submission_time"],
            "ride_datetime": r["ride_datetime"],
            "arrival_datetime": r["arrival_datetime"],
            "no_ride": r["no_ride"],
        }
    )

for sid, spot_rides in rides_by_spot.items():
    with open(os.path.join(by_spot_dir, f"{sid}.json"), "w") as f:
        json.dump({"spot": spot_details.get(sid, {}), "rides": spot_rides}, f)
logger.info(f"Wrote {len(rides_by_spot)} per-spot ride files")


# dist/spots.gpx: the whole map as GPX, for the menu's download link. Streamed so the
# 35k waypoints never exist as one tree (see hitch/scripts/spots_gpx.py).
def _spot_waypoints():
    for spot in spots_data:
        spot_id = generate_spot_id(spot["lat"], spot["lon"])
        last_ride = pd.Timestamp(spot["latest_ms"], unit="ms", tz="UTC").strftime("%Y-%m-%d") if spot.get("latest_ms") else None
        yield spot_waypoint(spot, spot_details.get(spot_id, {}), spot_id, last_ride)


gpx_path = os.path.join(dirs["dist"], "spots.gpx")
gpx_size = write_spots_gpx(gpx_path, _spot_waypoints(), len(spots_data), pd.Timestamp.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"))
logger.info(f"Wrote {gpx_path} ({gpx_size / 1e6:.1f} MB, {len(spots_data)} spots) (+ .gz sidecar)")

# TODO: Remove spots_with_destination.json - replaced by spots.json with ride filtering
# places_with_destination = places[~places.distance.isnull()]
# write_json_file(places_with_destination[point_columns], "spots_with_destination.json")

# Recent rides are used to display them in tabular format on a separate page
recent = rides_df.dropna(subset=["submission_time"]).sort_values("submission_time", ascending=False).iloc[:1000]
recent["url"] = "#" + recent.lat.astype(str) + "," + recent.lon.astype(str)
recent["text"] = rides_df.comment.fillna("") + " " + rides_df.extra_text.fillna("")
recent["hitchhiker_name"] = recent["hitchhiker_name"].str.replace("://", "", regex=False)
recent["distance"] = recent["distance"].round(1)
recent["submission_time"] = recent["submission_time"].astype(str)
recent["submission_time"] += np.where(~recent.ride_datetime.isnull(), " 🕒", "")
write_json_file(recent[["url", "submission_time", "hitchhiker_name", "rating", "distance", "text"]], "spots_recent.json")


def _card_when(row):
    """The date a ride card prints: when the ride was hitched, falling back to when it
    was typed up. Same rule as user._extract_ride_info's `when` — "2026-08-01" on a ride
    from last summer is the record's birthday, not the ride's."""
    for value in (row.get("ride_datetime"), row.get("submission_time")):
        if pd.notna(value):
            return pd.Timestamp(value).strftime("%Y-%m-%d %H:%M")
    return ""


def _build_ride_card(row):
    """A ride-card dict for one rides_df row.

    The keys are the contract the shared hitch/templates/_ride_card.html macro renders,
    the same one user._extract_ride_info and main._ride_to_card emit, so a ride on the
    leaderboard looks exactly like the same ride on a profile.
    """
    return {
        "d_tag": row["d"],
        "when": _card_when(row),
        "rating": int(row["rating"]) if pd.notna(row["rating"]) else 0,
        "comment": row["comment"] if pd.notna(row["comment"]) else "",
        "hitchhiker_name": row["hitchhiker_name"],
        "pickup_lat": row["lat"],
        "pickup_lon": row["lon"],
        # Both ends are sent so the card's map thumbnail can mark where the ride started
        # and where it ended, as the route planner does.
        "destination_lat": row["dest_lat"] if pd.notna(row["dest_lat"]) else None,
        "destination_lon": row["dest_lon"] if pd.notna(row["dest_lon"]) else None,
        "wait_min": int(row["wait"]) if pd.notna(row["wait"]) else None,
        "distance_km": round(float(row["distance"]), 1) if pd.notna(row["distance"]) else None,
        "images": ride_image_urls.get(row["d"], []),
        "no_ride": bool(row["no_ride"]) if pd.notna(row.get("no_ride")) else False,
    }


# Precompute the 10 longest rides for the leaderboard so the /leaderboard route can
# just read this file instead of scanning and haversine-ing every ride on each request.
# Only rank rides the hitchhiker actually logged a destination for: a destination we mined
# from comment text can be mis-geocoded (a same-named city on another continent), which would
# otherwise fabricate a "12,000 km" ride at the top of the board. See merge_derived_destinations.
longest = rides_df[~rides_df["dest_is_derived"]].dropna(subset=["distance"]).sort_values("distance", ascending=False).iloc[:10]
write_json_file([_build_ride_card(row) for _, row in longest.iterrows()], "longest_rides.json")

# Precompute the "longest distance in 24h" leaderboard. Per named hitchhiker, find the
# best contiguous sequence of their rides whose span (first departure -> last arrival)
# fits in 24h, maximizing total distance. Only rides with a real username AND both a
# departure and arrival time qualify. The leaderboard then ranks users by that total and
# lists every ride in the winning window. Done here (not per-request) to keep /leaderboard fast.
WINDOW_24H = pd.Timedelta(hours=24)

# Normalize departure/arrival to UTC so windows can be compared regardless of the
# timezone offsets stored in the original event timestamps.
window_df = rides_df.copy()
window_df["start_dt"] = pd.to_datetime(window_df["ride_datetime"], utc=True, errors="coerce")
window_df["end_dt"] = pd.to_datetime(window_df["arrival_datetime"], utc=True, errors="coerce")
qualifying_24h = window_df[
    (window_df["hitchhiker_name"] != "Anonymous")
    & window_df["start_dt"].notna()
    & window_df["end_dt"].notna()
    & window_df["distance"].notna()
    # Same rule as the longest-ride board: rank only logged destinations, never mined ones.
    # (A derived destination has no arrival_time so end_dt is already NaN, but be explicit.)
    & ~window_df["dest_is_derived"]
]

leaderboard_24h = []
for name, group in qualifying_24h.groupby("hitchhiker_name"):
    # Order rides by departure; a "sequence" is a contiguous run in this order.
    group = group.sort_values("start_dt").reset_index(drop=True)
    starts = group["start_dt"].tolist()
    ends = group["end_dt"].tolist()
    dists = group["distance"].tolist()
    n = len(group)

    best_sum, best_range = -1.0, None
    for i in range(n):
        running_sum = 0.0
        max_end = ends[i]
        for j in range(i, n):
            # max_end is non-decreasing as j grows, so once the span exceeds 24h
            # no further j can bring it back under — stop extending this window.
            if ends[j] > max_end:
                max_end = ends[j]
            if (max_end - starts[i]) > WINDOW_24H:
                break
            running_sum += dists[j]
            if running_sum > best_sum:
                best_sum = running_sum
                best_range = (i, j)

    if best_range is None:
        continue
    i, j = best_range
    window = group.iloc[i : j + 1]
    leaderboard_24h.append(
        {
            "hitchhiker_name": name,
            "total_distance": int(round(best_sum)),
            "window_start": starts[i].strftime("%Y-%m-%d %H:%M"),
            "window_end": window["end_dt"].max().strftime("%Y-%m-%d %H:%M"),
            "rides": [_build_ride_card(row) for _, row in window.iterrows()],
        }
    )

leaderboard_24h.sort(key=lambda e: e["total_distance"], reverse=True)
write_json_file(leaderboard_24h[:10], "longest_24h.json")

# Precompute the race standings (see RACES.md for the definition and rules) so /races is
# a file read. Qualifying rides: a named hitchhiker, a logged destination (never a mined
# one — a mis-geocoded city would fabricate an impossible finish) and a departure time.
# An arrival time is used when present and estimated from the leg distance otherwise;
# see races.estimate_arrival for why insisting on a real arrival is not an option.
#
# Rebuilt at most hourly, not on every 10-minute show run: a podium barely moves within an
# hour, and this is the only output here that scans every hitchhiker's rides per race.
# Deliberately NOT in should_regenerate_json's canary list — an hour-old races.json there
# would drag a whole show run out of its skip path even when no ride changed.
RACES_MAX_AGE_S = 3600
races_path = os.path.join(dirs["dist"], "races.json")
races_md_path = os.path.join(dirs["root"], "RACES.md")
races_mtime = os.path.getmtime(races_path) if os.path.exists(races_path) else None
races_stale = (
    current_app.config.get("FORCE_REGENERATE", False)
    or races_mtime is None
    or (time.time() - races_mtime) >= RACES_MAX_AGE_S
    # An edited RACES.md is a deliberate change (a race added, a date retuned) and should
    # not wait out the hour.
    or (os.path.exists(races_md_path) and os.path.getmtime(races_md_path) > races_mtime)
)

if not races_stale:
    logger.info(f"races.json is {int(time.time() - races_mtime)}s old (< {RACES_MAX_AGE_S}s), skipping race standings")
else:
    race_df = window_df[
        (window_df["hitchhiker_name"] != "Anonymous")
        & window_df["start_dt"].notna()
        & window_df["dest_lat"].notna()
        & window_df["dest_lon"].notna()
        & window_df["distance"].notna()
        & ~window_df["dest_is_derived"]
    ]
    race_rides_by_name: dict[str, list] = {}
    for _, row in race_df.iterrows():
        start = row["start_dt"].to_pydatetime()
        end = row["end_dt"].to_pydatetime() if pd.notna(row["end_dt"]) else None
        estimated = end is None or end < start
        if estimated:
            end = estimate_arrival(start, row["lat"], row["lon"], row["dest_lat"], row["dest_lon"])
        race_rides_by_name.setdefault(row["hitchhiker_name"], []).append(
            {
                "lat": row["lat"],
                "lon": row["lon"],
                "dest_lat": row["dest_lat"],
                "dest_lon": row["dest_lon"],
                "start": start,
                "end": end,
                "estimated": estimated,
            }
        )
    # Read the outgoing podiums before overwriting the file: whoever is on a podium now
    # but wasn't on the previous one just entered the top 3, and that is the moment worth
    # a notification.
    previous_podiums = load_race_podiums(races_path)
    new_races = build_races(races_md_path, race_rides_by_name)
    write_json_file(new_races, "races.json")
    notify_new_race_podiums(previous_podiums, new_races)

# duplicates["from_url"] = "#" + duplicates.from_lat.astype(str) + "," + duplicates.from_lon.astype(str)
# duplicates["to_url"] = "#" + duplicates.to_lat.astype(str) + "," + duplicates.to_lon.astype(str)
# duplicates_data = duplicates[["id", "from_url", "to_url", "distance", "reviewed", "accepted"]].to_dict(orient="records")
# write_json_file(duplicates[["id", "from_url", "to_url", "distance", "reviewed", "accepted"]], "rides_df_duplicates.json")

logger.info("Data preparation completed")


def generate_heatmap_data():
    """Generate heatmap data and return the image overlay data."""
    import matplotlib.colors as colors
    import numpy as np
    from heatchmap.gpmap import GPMap
    from heatchmap.map_based_model import BOUNDARIES, BUCKETS

    # Use truncated buckets and boundaries as in hitchhiking.py
    BUCKETS = BUCKETS[:-1]
    BOUNDARIES = BOUNDARIES[:-1]

    cmap = colors.ListedColormap(BUCKETS)
    norm = colors.BoundaryNorm(BOUNDARIES, cmap.N, clip=True)
    cmap.set_bad(color="#000000", alpha=0.0)  # opaque for NaN values (sea)

    # GPMap uses a sklearn model to predict waiting times from sklearn version 1.6.0
    # although this project uses a more recent sklearn version, this should not cause issues
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=InconsistentVersionWarning)
        gpmap = GPMap()

    gpmap.get_map_grid()
    gpmap.get_landmass_raster()

    image = gpmap.raw_raster
    image = np.where(gpmap.landmass_raster, image, np.nan)
    image = norm(image).data
    # Apply the colormap to scalars
    colors_data = cmap(image)

    uncertainties = gpmap.uncertainties
    # no uncertainties for sea -> becomes fully transparent
    uncertainties = np.where(gpmap.landmass_raster, uncertainties, uncertainties.max())
    # Normalize uncertainties
    uncertainties = (uncertainties - uncertainties.min()) / (uncertainties.max() - uncertainties.min())
    uncertainties = 1 - uncertainties

    # Combine RGB values with the opacity
    rgba_array = np.empty_like(colors_data)
    rgba_array[:, :, :3] = colors_data[:, :, :3]  # RGB
    rgba_array[:, :, 3] = uncertainties

    # Create legend data
    legend_data = {
        "colors": BUCKETS.tolist() if hasattr(BUCKETS, "tolist") else list(BUCKETS),
        "boundaries": BOUNDARIES[:-1].tolist() if hasattr(BOUNDARIES[:-1], "tolist") else list(BOUNDARIES[:-1]),
        "vmin": float(BOUNDARIES[0]),
        "vmax": float(BOUNDARIES[-1]),
        "caption": "Waiting time to catch a ride by hitchhiking (minutes)",
    }

    # Save as PNG image instead of JSON pixel data (196MB JSON → ~100KB PNG)
    from PIL import Image

    rgba_uint8 = (rgba_array * 255).astype(np.uint8)
    img = Image.fromarray(rgba_uint8, mode="RGBA")
    png_path = os.path.join(dirs["dist"], "heatmap.png")
    img.save(png_path, optimize=True)
    logger.info(f"Heatmap PNG saved to {png_path} ({os.path.getsize(png_path) // 1024}KB)")

    return {
        "image_url": "/heatmap.png",
        "bounds": [[-56, -180], [80, 180]],
        "legend": legend_data,
    }


# Written once every RIDE data file above is on disk, and deliberately BEFORE the optional
# heatmap step: /pending_rides.json only cares whether the ride files are current, and the
# heatmap is both unrelated to rides and by far the most likely thing here to die (it peaks
# ~1.9 GB and has been OOM-killed on this host, which bypasses its try/except and would
# otherwise leave the timestamp permanently unwritten).
write_json_file({"ts": snapshot_ts}, "generated_at.json")

# Generate heatmap data file (unless disabled — see GENERATE_HEATMAP in settings.py)
if current_app.config.get("GENERATE_HEATMAP", True):
    logger.info("Generating heatmap data")
    try:
        heatmap_data = generate_heatmap_data()
        write_json_file(heatmap_data, "heatmap.json")
        logger.info("Heatmap data generated successfully")
    except Exception as e:
        logger.error(f"Failed to generate heatmap data: {e}")
        logger.info("Continuing without heatmap data")
else:
    logger.info("Heatmap generation disabled")

logger.info("All data preparation completed")
logger.info("SHOW SCRIPT FINISHED")
