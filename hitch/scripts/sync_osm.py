"""Script to get official hitchhiking spots from OpenStreetMap using Overpass API and store them in the database."""
import logging

import requests

from hitch.extensions import db
from hitch.models import OsmHitchhikingSpot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

overpass_url = "https://overpass-api.de/api/interpreter"
# official hitchhiking spots on OSM use the tag highway=hitchhiking
# see https://wiki.openstreetmap.org/wiki/Tag:highway=hitchhiking
overpass_query = """
[out:json][timeout:25];
nwr["highway"="hitchhiking"];
out meta;
"""

response = requests.post(overpass_url, data={'data': overpass_query})
data = response.json()

# Extract nodes
elements = data['elements']
nodes = [el for el in elements if el['type'] == 'node']

# Save fetched hitchhiking spots into the database
logger.info("Saving fetched hitchhiking spots into the database...")

# Remove all existing spots for a fresh start
db.session.query(OsmHitchhikingSpot).delete()
db.session.commit()

for node in nodes:
    spot = OsmHitchhikingSpot(
        id=node['id'],
        latitude=node['lat'],
        longitude=node['lon'],
        tags=node.get('tags', {}),
        timestamp=node.get('timestamp'),
        user=node.get('user'),
        uid=node.get('uid'),
    )
    db.session.add(spot)
db.session.commit()

logger.info(f"Saved {len(nodes)} hitchhiking spots from OSM into the database.")