import requests

from hitch.extensions import db
from hitch.models import OSMHitchhikingSpot

overpass_url = "https://overpass-api.de/api/interpreter"
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
print("Saving fetched hitchhiking spots into the database...")

# Remove all existing spots for a fresh start
db.session.query(OSMHitchhikingSpot).delete()
db.session.commit()

for node in nodes:
    spot = OSMHitchhikingSpot(
        osm_id=node['id'],
        latitude=node['lat'],
        longitude=node['lon'],
        tags=node.get('tags', {}),
        timestamp=node.get('timestamp'),
        user=node.get('user'),
        uid=node.get('uid'),
    )
    db.session.add(spot)
db.session.commit()