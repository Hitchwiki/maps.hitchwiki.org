"""Script to get official hitchhiking spots from OpenStreetMap using Overpass API and store them in the database."""

import logging
import time

import requests

from hitch.extensions import db
from hitch.models import OsmHitchhikingSpot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

overpass_url = "https://overpass-api.de/api/interpreter"
# official hitchhiking spots on OSM use the tag highway=hitchhiking
# see https://wiki.openstreetmap.org/wiki/Tag:highway=hitchhiking
overpass_query = """
[out:json][timeout:90];
nwr["highway"="hitchhiking"];
out meta;
"""

logger.info(f"SYNC OSM SCRIPT STARTED — querying Overpass at {overpass_url}")

# Overpass mirrors reject the default `python-requests/X` User-Agent with HTTP 406; identify ourselves explicitly.
headers = {"User-Agent": "maps.hitchwiki.org sync_osm (+https://maps.hitchwiki.org)"}
# overpass-api.de answers 429/504 under load, and can answer 200 with a `remark` and a truncated element list when
# a query runs out of time or memory. Retry across two mirrors, and only accept a response with no remark.
OVERPASS_MIRRORS = [overpass_url, "https://overpass.private.coffee/api/interpreter"]
data = None
for attempt in range(1, 5):
    if attempt > 1:
        time.sleep(20 * (attempt - 1))
    url = OVERPASS_MIRRORS[(attempt - 1) % len(OVERPASS_MIRRORS)]
    try:
        response = requests.post(url, data={"data": overpass_query}, headers=headers, timeout=120)
        logger.info(f"Overpass {url} attempt {attempt}: status={response.status_code}, body_bytes={len(response.content)}")
        if not response.ok:
            # Log the body so 4xx/5xx tell us *why* (Overpass returns the reason in plain text/HTML)
            logger.error(f"Overpass body: {response.text[:1000]}")
            continue
        candidate = response.json()
        if candidate.get("remark"):
            logger.error(f"Overpass remark (result may be partial): {candidate['remark'][:300]}")
            continue
        data = candidate
        break
    except (requests.RequestException, ValueError) as exc:
        logger.error(f"Overpass {url} attempt {attempt} failed: {exc}")
if data is None:
    logger.error("Overpass gave no complete answer after 4 attempts — aborting without touching the database")
    raise SystemExit(1)

elements = data.get("elements", [])
nodes = [el for el in elements if el["type"] == "node"]
logger.info(f"Parsed {len(elements)} elements, {len(nodes)} nodes")

# Refuse to wipe the table if Overpass returned nothing — protects against transient API failures leaving us with 0 spots
if not nodes:
    logger.error("Overpass returned 0 nodes — aborting without touching the database")
    raise SystemExit(1)

prior_count = db.session.query(OsmHitchhikingSpot).count()
logger.info(f"Replacing {prior_count} existing spots with {len(nodes)} fresh ones")

db.session.query(OsmHitchhikingSpot).delete()
db.session.commit()

for node in nodes:
    spot = OsmHitchhikingSpot(
        id=node["id"],
        latitude=node["lat"],
        longitude=node["lon"],
        tags=node.get("tags", {}),
        timestamp=node.get("timestamp"),
        user=node.get("user"),
        uid=node.get("uid"),
    )
    db.session.add(spot)
db.session.commit()

final_count = db.session.query(OsmHitchhikingSpot).count()
logger.info(f"SYNC OSM SCRIPT FINISHED — {final_count} spots saved (prior: {prior_count})")
