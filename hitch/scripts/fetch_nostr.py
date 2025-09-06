import subprocess
import logging
import os
import json
from hitch.helpers import get_dirs
from hitch.models import RideEvent, db
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

dirs = get_dirs()

logger.info("Starting the Node.js script...")
script_dir = '/app/hitch/scripts/fetch_hitchhiking_events'
command = ['node', 'dist/index.js']
subprocess.run(command, cwd=script_dir, check=True)
logger.info("Node.js script finished.")

with open(os.path.join(dirs["dist"], "allPosts.json")) as f:
    all_posts = json.load(f)


### Saving into database to efficiently query the rides later
logger.info("Saving fetched rides into the database...")

# Fresh start with new fetch of rides from Nostr
db.session.query(RideEvent).delete()
db.session.commit()

for post in all_posts:
        # Parse the 'content' field from JSON string to dict
        content_json = json.loads(post.get("content", "{}"))

        # Extract 'expiration', 'd', and 'published_at' from tags
        tags_dict = {tag[0]: tag[1] for tag in post.get("tags", []) if len(tag) == 2}
        expiration = tags_dict.get("expiration")
        d = tags_dict.get("d")
        published_at = tags_dict.get("published_at")

        ride_event = RideEvent(
            id=post.get("id"),
            kind=post.get("kind"),
            pubkey=post.get("pubkey"),
            sig=post.get("sig"),
            content=content_json,
            created_at=post.get("created_at"),
            source=content_json.get("source"),
            license=content_json.get("license"),
            submission_time=content_json.get("submission_time"),
            rating=content_json.get("rating"),
            expiration=expiration,
            d=d,
            published_at=published_at,
            tags=post.get("tags"),
        )
        db.session.add(ride_event)
db.session.commit()