import json
import logging
import os
import subprocess

from hitch.extensions import db
from hitch.helpers import get_dirs
from hitch.models import RideEvent
from hitch.scripts.map_revision import mark_map_data_dirty
from hitch.scripts.nostr_ride_parsing import parse_post_to_ride_fields

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

dirs = get_dirs()

logger.info("Starting the Node.js script...")
script_dir = "/app/hitch/scripts/fetch_hitchhiking_events"
command = ["node", "dist/index.js"]
subprocess.run(command, cwd=script_dir, check=True)
logger.info("Node.js script finished.")

with open(os.path.join(dirs["dist"], "allPosts.json")) as f:
    all_posts = json.load(f)

# Parse all posts BEFORE touching the database. We need the valid-ride count up front
# so we can decide whether to trust this fetch — see the guard below.
ride_events = []
skipped = 0
for post in all_posts:
    fields = parse_post_to_ride_fields(post)
    if fields is None:
        skipped += 1
        continue
    ride_events.append(RideEvent(**fields))

logger.info(f"Skipped {skipped} posts with empty or invalid content")

### Saving into database to efficiently query the rides later
logger.info("Saving fetched rides into the database...")

# Guard against a transient relay failure wiping all ride data. Because the save below
# is a destructive delete-and-recreate of the whole ride_event table, a fetch that comes
# back empty (or with suspiciously few events) would otherwise zero out every ride —
# breaking /ride/<d_tag> (404s) and the leaderboard (all-zero counts) until the next good
# fetch. The relay only ever gains rides; a large drop means the fetch failed, not that
# thousands of rides were really deleted, so we keep the existing table and bail out.
# Override the tolerated drop via FETCH_NOSTR_MIN_RIDE_FRACTION (default 0.5 = 50%).
current_count = db.session.query(RideEvent).count()
fetched_count = len(ride_events)
min_fraction = float(os.environ.get("FETCH_NOSTR_MIN_RIDE_FRACTION", "0.5"))
if current_count > 0 and fetched_count < current_count * min_fraction:
    logger.error(
        f"Aborting DB rebuild: fetched {fetched_count} valid rides but the table currently "
        f"holds {current_count} (below the {min_fraction:.0%} threshold). Treating this as a "
        f"failed fetch and keeping existing data. Set FETCH_NOSTR_MIN_RIDE_FRACTION to override."
    )
    raise SystemExit(1)

# Fresh start with new fetch of rides from Nostr
db.session.query(RideEvent).delete()
db.session.commit()

db.session.add_all(ride_events)
db.session.commit()
mark_map_data_dirty(dirs["dist"])

logger.info(f"Saved {fetched_count} rides into the database")
logger.info("FETCH NOSTR SCRIPT FINISHED")
