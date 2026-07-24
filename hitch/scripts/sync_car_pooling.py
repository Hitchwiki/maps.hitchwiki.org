"""Script to get car pooling spots from OpenStreetMap using Overpass API and store them in the database."""

import logging

import requests

from hitch.extensions import db
from hitch.models import OsmCarPoolingSpot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

overpass_url = "https://overpass-api.de/api/interpreter"
# Car pooling spots on OSM use the tag amenity=car_pooling
# see https://wiki.openstreetmap.org/wiki/Tag:amenity%3Dcar_pooling
# `out center` ensures ways/relations get a representative lat/lon (they have no direct coords).
overpass_query = """
[out:json][timeout:25];
nwr["amenity"="car_pooling"];
out center meta;
"""

logger.info(f"SYNC CAR POOLING SCRIPT STARTED — querying Overpass at {overpass_url}")

# Overpass mirrors reject the default `python-requests/X` User-Agent with HTTP 406; identify ourselves explicitly.
headers = {"User-Agent": "maps.hitchwiki.org sync_car_pooling (+https://maps.hitchwiki.org)"}
response = requests.post(overpass_url, data={"data": overpass_query}, headers=headers, timeout=60)
logger.info(f"Overpass responded: status={response.status_code}, body_bytes={len(response.content)}")
if not response.ok:
    logger.error(f"Overpass body: {response.text[:1000]}")
response.raise_for_status()

data = response.json()
elements = data.get("elements", [])
logger.info(f"Parsed {len(elements)} elements")

# Refuse to wipe the table if Overpass returned nothing — protects against transient API failures leaving us with 0 spots
if not elements:
    logger.error("Overpass returned 0 elements — aborting without touching the database")
    raise SystemExit(1)

prior_count = db.session.query(OsmCarPoolingSpot).count()
logger.info(f"Replacing {prior_count} existing car pooling spots with {len(elements)} fresh ones")

db.session.query(OsmCarPoolingSpot).delete()
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

    db.session.add(
        OsmCarPoolingSpot(
            id=el["id"],
            osm_type=el["type"],
            latitude=lat,
            longitude=lon,
            tags=el.get("tags", {}),
            timestamp=el.get("timestamp"),
            user=el.get("user"),
            uid=el.get("uid"),
        )
    )
db.session.commit()

final_count = db.session.query(OsmCarPoolingSpot).count()
logger.info(f"SYNC CAR POOLING SCRIPT FINISHED — {final_count} spots saved (prior: {prior_count}, skipped: {skipped})")
