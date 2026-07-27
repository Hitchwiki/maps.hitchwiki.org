"""Script to get official hitchhiking spots from OpenStreetMap using Overpass API and store them in the database."""

import logging

import requests

from hitch.extensions import db
from hitch.models import OsmHitchhikingSpot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

overpass_url = "https://overpass-api.de/api/interpreter"
# official hitchhiking spots on OSM use the tag highway=hitchhiking
# see https://wiki.openstreetmap.org/wiki/Tag:highway=hitchhiking
overpass_query = """
[out:json][timeout:25];
nwr["highway"="hitchhiking"];
out meta;
"""

logger.info(f"SYNC OSM SCRIPT STARTED — querying Overpass at {overpass_url}")

# Overpass mirrors reject the default `python-requests/X` User-Agent with HTTP 406; identify ourselves explicitly.
headers = {"User-Agent": "maps.hitchwiki.org sync_osm (+https://maps.hitchwiki.org)"}
response = requests.post(overpass_url, data={"data": overpass_query}, headers=headers, timeout=60)
logger.info(f"Overpass responded: status={response.status_code}, body_bytes={len(response.content)}")
if not response.ok:
    # Log the body so 4xx/5xx tell us *why* (Overpass returns the reason in plain text/HTML)
    logger.error(f"Overpass body: {response.text[:1000]}")
response.raise_for_status()

data = response.json()
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
