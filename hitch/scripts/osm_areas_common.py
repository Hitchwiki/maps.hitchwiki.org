"""Shared helpers for the OSM polygon sync scripts (sync_service_areas, sync_road_islands).

Both scripts work the same way: take the existing hitchhiking spots, keep only the
ones that sit close to a neighbour (an isolated spot can never be co-grouped with
another, so there is nothing to gain from querying OSM around it), and run one Overpass
query per such cluster. This module holds the bits they share so the two scripts only
differ in the OSM query and the geometry they build from the response.

These are slow, polite, *resumable* one-off jobs (run manually, thousands of Overpass
calls — not scheduled via cron; see the README):
  * `query_overpass` throttles between calls and backs off on HTTP 429 so we don't get
    the host IP blocked from the shared public endpoint.
  * `resume_clusters` snapshots the cluster list to disk on the first run and records how
    far we got, so a crash / OOM / container restart mid-run resumes instead of starting
    over (and a concurrent `show` run rewriting spots.json can't shift our indices).
  * The scripts commit to the DB incrementally, so partial progress is never lost.

Plain importable module — no top-level side effects.
"""

import json
import logging
import os
import time

import numpy as np
import requests
from sklearn.cluster import DBSCAN

from hitch.helpers import get_dirs

logger = logging.getLogger(__name__)

# Standard public Overpass endpoint. These are one-off manual jobs, so the throttle +
# 429 back-off below keep us within the shared instance's limits rather than relying on a
# faster mirror. Overridable via env if you want to point at a private/bulk instance.
OVERPASS_URL = os.environ.get("OVERPASS_BULK_URL", "https://overpass-api.de/api/interpreter")
# Overpass mirrors reject the default `python-requests/X` User-Agent with HTTP 406; identify ourselves explicitly.
OVERPASS_HEADERS = {"User-Agent": "maps.hitchwiki.org sync_areas (+https://maps.hitchwiki.org)"}
# Polite spacing between successful Overpass calls — this is a bulk job against a shared
# free endpoint, so we trade speed for not getting rate-limited / banned.
THROTTLE_S = 1.5

EARTH_RADIUS_M = 6_371_000
# Only spots within this distance of a neighbour are worth an Overpass lookup: a lone
# spot can't merge with anything, and a gas station / junction comfortably fits inside it.
CLUSTER_RADIUS_M = 800


def load_spot_coords():
    """Return the merged hitchhiking spots as an (N, 2) lat/lon array.

    Reads dist/spots.json — the already deduped/merged spot list produced by show.py —
    instead of re-parsing ride_event stops, so we query OSM around real map markers.
    """
    spots_path = os.path.join(get_dirs()["dist"], "spots.json")
    if not os.path.exists(spots_path):
        logger.error(f"{spots_path} not found — run `flask generate show` first")
        raise SystemExit(1)
    with open(spots_path) as f:
        spots = json.load(f)
    coords = np.array([[s["lat"], s["lon"]] for s in spots], dtype=float)
    logger.info(f"Loaded {len(coords)} spot coordinates from {spots_path}")
    return coords


def build_clusters(coords, radius_m=CLUSTER_RADIUS_M):
    """Group spots within radius_m of each other; drop isolated spots.

    Returns a list of clusters, each a list of [lat, lon] pairs (JSON-serializable so it
    can be snapshotted). DBSCAN with min_samples=2 labels lone spots as -1 (noise).
    """
    if len(coords) < 2:
        return []
    labels = DBSCAN(
        eps=radius_m / EARTH_RADIUS_M,
        min_samples=2,
        metric="haversine",
        algorithm="ball_tree",
    ).fit_predict(np.radians(coords))
    clusters = [coords[labels == label].tolist() for label in sorted(set(labels) - {-1})]
    logger.info(f"Found {len(clusters)} spot clusters (≥2 spots within {radius_m} m); dropped {(labels == -1).sum()} isolated")
    return clusters


def query_overpass(query, timeout=180, retries=4):
    """POST an Overpass query and return its parsed `elements`, throttled and 429-aware.

    A single failing location must not abort a multi-hour run, so transient errors are
    logged and swallowed (return []). On HTTP 429 we honour Retry-After and try again.
    """
    for attempt in range(retries):
        try:
            response = requests.post(OVERPASS_URL, data={"data": query}, headers=OVERPASS_HEADERS, timeout=timeout)
        except requests.RequestException as err:
            logger.warning(f"Overpass request error (attempt {attempt + 1}): {err}")
            time.sleep(5)
            continue
        if response.status_code == 429:
            wait = int(response.headers.get("Retry-After") or 30)
            logger.warning(f"Overpass 429 rate-limited — backing off {wait}s (attempt {attempt + 1})")
            time.sleep(wait)
            continue
        if not response.ok:
            logger.warning(f"Overpass {response.status_code}: {response.text[:200]}")
            return []
        # Be polite: space out successful calls regardless of how fast the server answered.
        time.sleep(THROTTLE_S)
        try:
            return response.json().get("elements", [])
        except ValueError:
            return []
    logger.warning("Overpass gave up after retries")
    return []


# --- resumable checkpointing -------------------------------------------------
# Snapshot + progress live in the (bind-mounted, so restart-surviving) db/ dir as
# hidden JSON files, one pair per script name.


def _checkpoint_paths(name):
    db_dir = get_dirs()["db"]
    return (
        os.path.join(db_dir, f".{name}.snapshot.json"),
        os.path.join(db_dir, f".{name}.progress.json"),
    )


def resume_clusters(name, coords):
    """Return (clusters, start_index).

    First run: build clusters from `coords`, snapshot them, start at 0. Subsequent runs
    while a checkpoint exists: reuse the snapshot (so spots.json changing mid-run can't
    renumber the work) and continue from the saved index.
    """
    snapshot_path, progress_path = _checkpoint_paths(name)
    if os.path.exists(snapshot_path) and os.path.exists(progress_path):
        with open(snapshot_path) as f:
            clusters = json.load(f)
        with open(progress_path) as f:
            start = json.load(f).get("next_index", 0)
        logger.info(f"Resuming {name}: {start}/{len(clusters)} clusters already done")
        return clusters, start
    clusters = build_clusters(coords)
    with open(snapshot_path, "w") as f:
        json.dump(clusters, f)
    with open(progress_path, "w") as f:
        json.dump({"next_index": 0}, f)
    logger.info(f"Fresh {name}: {len(clusters)} clusters to process")
    return clusters, 0


def save_progress(name, next_index):
    _, progress_path = _checkpoint_paths(name)
    with open(progress_path, "w") as f:
        json.dump({"next_index": next_index}, f)


def clear_checkpoint(name):
    """Remove snapshot + progress so the next run starts fresh (call on completion)."""
    for path in _checkpoint_paths(name):
        if os.path.exists(path):
            os.remove(path)


def cluster_bbox(cluster, margin_m=100):
    """(south, west, north, east) covering a cluster's [lat, lon] members plus a margin."""
    lats = [p[0] for p in cluster]
    lons = [p[1] for p in cluster]
    margin = margin_m / (EARTH_RADIUS_M * np.pi / 180)  # metres → degrees
    return min(lats) - margin, min(lons) - margin, max(lats) + margin, max(lons) + margin
