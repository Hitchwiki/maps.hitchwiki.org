"""Fetch fuel / gas stations from OpenStreetMap (Overpass API) and store them in the database.

Unlike sync_car_pooling / sync_osm, a *global* `amenity=fuel` query is far too large
for the public Overpass servers (hundreds of thousands of elements) and reliably 504s.
Fuel data is only ever used to flag hitchhiking spots that sit *at* a gas station
(show.py, 100 m match), so we only need fuel near existing spots. We therefore read the
spot coordinates from the already-generated dist/spots.json, reduce them to 1° tiles, and
query Overpass for fuel only inside those tiles — batched into a handful of union queries.
"""
import json
import logging
import math
import os
import time

import requests

from hitch.extensions import db
from hitch.helpers import get_dirs
from hitch.models import OsmFuelStationSpot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

overpass_url = "https://overpass-api.de/api/interpreter"
# Overpass mirrors reject the default `python-requests/X` User-Agent with HTTP 406; identify ourselves explicitly.
headers = {"User-Agent": "maps.hitchwiki.org sync_fuel (+https://maps.hitchwiki.org)"}

# Fuel / gas stations on OSM use amenity=fuel — https://wiki.openstreetmap.org/wiki/Tag:amenity%3Dfuel
# Each tile is one whole degree; bboxes are padded by this margin so a fuel station just
# outside a tile but within the 100 m match radius of a spot near the tile edge is still fetched.
TILE_MARGIN_DEG = 0.02
# Number of tile bboxes unioned into a single Overpass request. Keeps the request count
# low (~30 for the whole world) while each request stays small and fast — fewer requests
# also means fewer chances of hitting the public instance's per-slot 429 rate limit.
TILES_PER_QUERY = 120
# Pause between requests to stay friendly to the shared public Overpass instance.
SLEEP_BETWEEN_QUERIES_S = 5
# The public Overpass instance runs a small pool of slots and returns HTTP 429 when
# none are free; retry with exponential backoff rather than aborting the whole run.
MAX_RETRIES = 6
RETRY_BASE_SLEEP_S = 30


def load_spot_tiles():
    """Return the set of (floor(lat), floor(lon)) 1° tiles that contain a hitchhiking spot."""
    spots_path = os.path.join(get_dirs()["dist"], "spots.json")
    if not os.path.exists(spots_path):
        logger.error(f"{spots_path} does not exist yet — run `show` first. Aborting without touching the database.")
        raise SystemExit(1)
    with open(spots_path) as fh:
        spots = json.load(fh)
    tiles = {(math.floor(s["lat"]), math.floor(s["lon"])) for s in spots if s.get("lat") is not None and s.get("lon") is not None}
    logger.info(f"Read {len(spots)} spots → {len(tiles)} distinct 1° tiles to query")
    return sorted(tiles)


def build_query(tile_batch):
    """Build an Overpass query unioning an amenity=fuel bbox lookup for each tile in the batch."""
    lines = []
    for lat, lon in tile_batch:
        s = lat - TILE_MARGIN_DEG
        w = lon - TILE_MARGIN_DEG
        n = lat + 1 + TILE_MARGIN_DEG
        e = lon + 1 + TILE_MARGIN_DEG
        lines.append(f'  nwr["amenity"="fuel"]({s},{w},{n},{e});')
    union = "\n".join(lines)
    # `out center` ensures ways/relations (the forecourt area) get a representative lat/lon.
    return f"[out:json][timeout:180];\n(\n{union}\n);\nout center meta;\n"


def fetch_batch(query, batch_label):
    """POST one Overpass query, retrying with exponential backoff on 429 (no free slot)
    and 504 (server busy). Returns the parsed elements list."""
    for attempt in range(1, MAX_RETRIES + 1):
        response = requests.post(overpass_url, data={"data": query}, headers=headers, timeout=300)
        if response.ok:
            return response.json().get("elements", [])
        if response.status_code in (429, 504) and attempt < MAX_RETRIES:
            # Honour Retry-After when Overpass sends it, else exponential backoff.
            retry_after = response.headers.get("Retry-After")
            wait = int(retry_after) if (retry_after and retry_after.isdigit()) else RETRY_BASE_SLEEP_S * attempt
            logger.warning(f"{batch_label} got {response.status_code}; retry {attempt}/{MAX_RETRIES - 1} after {wait}s")
            time.sleep(wait)
            continue
        # A non-retryable status, or retries exhausted: surface it (raise_for_status logs below).
        logger.error(f"{batch_label} failed: status={response.status_code} body={response.text[:500]}")
        response.raise_for_status()
    raise RuntimeError(f"{batch_label}: exhausted retries")


logger.info(f"SYNC FUEL SCRIPT STARTED — querying Overpass at {overpass_url}")

tiles = load_spot_tiles()
batches = [tiles[i : i + TILES_PER_QUERY] for i in range(0, len(tiles), TILES_PER_QUERY)]
logger.info(f"Querying {len(tiles)} tiles in {len(batches)} batched requests")

# Dedupe across batches: padded bboxes of neighbouring tiles overlap, so the same
# station can appear in two batches. OSM (type, id) is the globally unique key.
elements_by_key = {}
for i, batch in enumerate(batches, 1):
    query = build_query(batch)
    batch_elements = fetch_batch(query, f"Batch {i}/{len(batches)}")
    for el in batch_elements:
        elements_by_key[(el["type"], el["id"])] = el
    logger.info(f"Batch {i}/{len(batches)}: {len(batch_elements)} elements ({len(elements_by_key)} unique so far)")
    if i < len(batches):
        time.sleep(SLEEP_BETWEEN_QUERIES_S)

elements = list(elements_by_key.values())
logger.info(f"Fetched {len(elements)} unique fuel stations near spots")

# Refuse to wipe the table if we got nothing — protects against transient API failures leaving us with 0 spots.
if not elements:
    logger.error("Overpass returned 0 elements — aborting without touching the database")
    raise SystemExit(1)

prior_count = db.session.query(OsmFuelStationSpot).count()
logger.info(f"Replacing {prior_count} existing fuel stations with {len(elements)} fresh ones")

db.session.query(OsmFuelStationSpot).delete()
db.session.commit()

skipped = 0
for el in elements:
    # Nodes carry lat/lon directly; ways/relations carry it under "center" thanks to `out center`.
    if el["type"] == "node":
        lat, lon = el.get("lat"), el.get("lon")
    else:
        center = el.get("center") or {}
        lat, lon = center.get("lat"), center.get("lon")

    if lat is None or lon is None:
        skipped += 1
        continue

    db.session.add(OsmFuelStationSpot(
        id=el["id"],
        osm_type=el["type"],
        latitude=lat,
        longitude=lon,
        tags=el.get("tags", {}),
        timestamp=el.get("timestamp"),
        user=el.get("user"),
        uid=el.get("uid"),
    ))
db.session.commit()

final_count = db.session.query(OsmFuelStationSpot).count()
logger.info(
    f"SYNC FUEL SCRIPT FINISHED — {final_count} stations saved (prior: {prior_count}, skipped: {skipped})"
)
