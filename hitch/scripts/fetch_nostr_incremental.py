import json
import logging
import os
import subprocess

from sqlalchemy import func, tuple_

from hitch.extensions import db
from hitch.helpers import get_dirs
from hitch.models import RideEvent
from hitch.scripts.map_revision import mark_map_data_dirty
from hitch.scripts.nostr_ride_parsing import parse_post_to_ride_fields

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

dirs = get_dirs()

# Incremental counterpart of fetch_nostr.py. The full script re-fetches the ENTIRE kind-36820
# history (75k+ events) every 30 min and re-serialises 100+ MB, pinning a full CPU core for a
# minute+ each run — pure waste to capture a handful of genuinely new rides. This one asks the
# relay only for events newer than the newest one we already hold, then upserts them, so the
# common case is sub-second.
#
# How edits are handled: kind 36820 is an addressable (replaceable) event. An edit reuses the
# same `d` tag under the same `pubkey`, but is re-published with a fresh `created_at` (~now) and
# therefore a new event `id`. Because every edit carries a brand-new timestamp, a `since =
# max(created_at)` query always returns it — even edits to years-old rides. We upsert keyed on
# the addressable coordinate (pubkey, d), newest-created_at-wins.
#
# NIP-09 deletions are handled below (we also fetch all kind-5 events). The only thing a `since`
# query still can't see is back-dated events, reconciled by the weekly full fetch_nostr.py.

# Fetch events at or after our newest stored timestamp. `since` is inclusive in the Nostr
# filter, so re-seeing the boundary event(s) is fine — the upsert below is idempotent. A NULL
# max (empty table) means "first ever run": leave SINCE unset so the node script does a full
# fetch.
max_created_at = db.session.query(func.max(RideEvent.created_at)).scalar()

script_dir = "/app/hitch/scripts/fetch_hitchhiking_events"
out_file = os.path.join(dirs["dist"], "newPosts.json")
del_file = os.path.join(dirs["dist"], "newDeletions.json")

env = dict(os.environ)
env["OUT_FILE"] = out_file
env["DEL_OUT_FILE"] = del_file
if max_created_at is not None:
    env["SINCE"] = str(int(max_created_at))
    logger.info(f"Fetching Nostr events with created_at >= {int(max_created_at)} (incremental)...")
else:
    logger.info("ride_event table is empty; fetching full history (first run)...")

subprocess.run(["node", "dist/index_incremental.js"], cwd=script_dir, check=True, env=env)
logger.info("Node.js script finished.")

with open(out_file) as f:
    fetched_posts = json.load(f)

# Parse first, so a malformed post can't leave a half-applied batch.
skipped = 0
parsed = []
for post in fetched_posts:
    fields = parse_post_to_ride_fields(post)
    if fields is None:
        skipped += 1
        continue
    parsed.append(fields)

logger.info(f"Fetched {len(fetched_posts)} events ({skipped} skipped for empty/invalid content, {len(parsed)} parsable)")

# Preload the existing rows for exactly the (pubkey, d) coordinates we just fetched, in one query,
# so the upsert is O(batch) DB lookups rather than one round-trip per event.
keys = [(f["pubkey"], f["d"]) for f in parsed]
existing = {}
if keys:
    for row in db.session.query(RideEvent).filter(tuple_(RideEvent.pubkey, RideEvent.d).in_(keys)).all():
        existing[(row.pubkey, row.d)] = row

inserted = 0
updated = 0
unchanged = 0
for fields in parsed:
    key = (fields["pubkey"], fields["d"])
    row = existing.get(key)
    if row is None:
        # Brand-new ride at this addressable coordinate.
        new_row = RideEvent(**fields)
        db.session.add(new_row)
        # Guard against the same (pubkey, d) appearing twice within one batch (e.g. a ride
        # edited twice since the last fetch): keep the newest and treat the rest as updates.
        existing[key] = new_row
        inserted += 1
    elif fields["created_at"] > (row.created_at or 0):
        # A newer revision (edit) of a ride we already hold. Overwrite every column, including
        # the primary-key `id`, since an edit produces a new event id under the same (pubkey, d).
        for col, val in fields.items():
            setattr(row, col, val)
        updated += 1
    else:
        # Same or older revision than what we have — nothing to do.
        unchanged += 1

if inserted or updated:
    db.session.commit()
    mark_map_data_dirty(dirs["dist"])
    logger.info(f"Upsert complete: {inserted} inserted, {updated} updated, {unchanged} unchanged")
else:
    logger.info(f"Skipping upsert commit: no rides inserted or updated ({unchanged} boundary event(s) unchanged)")

# --- Apply NIP-09 deletions ---
# Run after the upsert so that a ride which was edited (new id, re-inserted above) and then
# deleted in the same window still ends up removed. Each kind-5 event lists the deleted event
# ids in its `e` tags; we only honour a deletion when its author (pubkey) matches the stored
# ride's pubkey — NIP-09 restricts deletion to the original author, so a forged delete event
# cannot remove someone else's ride. Deleting an id we don't hold (or already removed) is a no-op.
with open(del_file) as f:
    deletions = json.load(f)

authorised_pubkeys_by_id = {}
for deletion in deletions:
    pubkey = deletion.get("pubkey")
    for tag in deletion.get("tags", []):
        if len(tag) >= 2 and tag[0] == "e":
            authorised_pubkeys_by_id.setdefault(tag[1], set()).add(pubkey)

removed = 0
if authorised_pubkeys_by_id:
    rows = db.session.query(RideEvent).filter(RideEvent.id.in_(list(authorised_pubkeys_by_id.keys()))).all()
    for row in rows:
        if row.pubkey in authorised_pubkeys_by_id.get(row.id, ()):
            db.session.delete(row)
            removed += 1
    if removed:
        db.session.commit()
        mark_map_data_dirty(dirs["dist"])
        logger.info(f"Committed {removed} authorised NIP-09 deletion(s)")
    else:
        logger.info("Skipping deletion commit: no authorised rides were removed")
else:
    logger.info("Skipping deletion commit: no NIP-09 deletion events were fetched")

logger.info(f"Applied deletions: {len(deletions)} kind-5 events seen, {removed} rides removed")
logger.info("FETCH NOSTR INCREMENTAL SCRIPT FINISHED")
