import json
import logging
import os
import shutil
import subprocess

from hitch.extensions import db
from hitch.helpers import get_dirs
from hitch.models import RideEvent
from hitch.scripts.nostr_ride_parsing import parse_post_to_ride_fields

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

dirs = get_dirs()

# The Node script overwrites the PUBLIC dist/allPosts.json / allPosts.csv before the DB guard below can
# veto a bad fetch (2026-11-16: the relay returned nothing, both files became "[]" / header-only and stayed
# public). Keep copies and put them back whenever this run does not complete a good fetch (IDEAS #1532).
_EXPORTS = [os.path.join(dirs["dist"], n) for n in ("allPosts.json", "allPosts.csv")]


def _backup_exports():
    for path in _EXPORTS:
        if os.path.exists(path):
            shutil.copy2(path, path + ".bak")


def _restore_exports():
    for path in _EXPORTS:
        if os.path.exists(path + ".bak"):
            shutil.copy2(path + ".bak", path)
            logger.error(f"Restored {os.path.basename(path)} from backup after a failed fetch")


_backup_exports()
logger.info("Starting the Node.js script...")
script_dir = "/app/hitch/scripts/fetch_hitchhiking_events"
command = ["node", "dist/index.js"]
try:
    subprocess.run(command, cwd=script_dir, check=True)
except Exception:
    _restore_exports()
    raise
logger.info("Node.js script finished.")

with open(os.path.join(dirs["dist"], "allPosts.json")) as f:
    all_posts = json.load(f)
if not all_posts:
    _restore_exports()
    raise SystemExit("Relay returned no posts; restored the previous public exports and kept the database")

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
    _restore_exports()
    raise SystemExit(1)

# Fresh start with new fetch of rides from Nostr
db.session.query(RideEvent).delete()
db.session.commit()

db.session.add_all(ride_events)
db.session.commit()

logger.info(f"Saved {fetched_count} rides into the database")
logger.info("FETCH NOSTR SCRIPT FINISHED")
