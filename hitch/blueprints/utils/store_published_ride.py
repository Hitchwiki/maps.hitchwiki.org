"""Write a ride this app just published to Nostr into the local `ride_event` table.

Lives in its own module rather than in `main` because `user` publishes rides too (a trip
save republishes its rides with the trip's reasons) and `main` imports `user` — so an
import the other way round would be circular.
"""

from flask import current_app

from hitch.extensions import db
from hitch.models import RideEvent
from hitch.scripts.nostr_ride_parsing import parse_post_to_ride_fields


def store_published_ride(event):
    """Write a ride we just published to Nostr straight into the local ride_event table.

    Without this the ride exists only on the relays until fetch_nostr_incremental runs
    (up to 5 min), so /ride/<d_tag> 404s and the author's own ride is missing from their
    profile. We parse our own signed event with parse_post_to_ride_fields — the exact
    function both fetch scripts use — so the row is identical to the one the cron would
    have written, and the cron's upsert then classifies it "unchanged".

    Upsert keyed on the addressable coordinate (pubkey, d), as in
    fetch_nostr_incremental.py. `>=` rather than `>` on created_at: we are the publisher,
    so our event is by definition the newest revision even if an edit lands in the same
    second as the original.

    Known gap: pynostr does not check the relay's OK notice, so a silently rejected event
    leaves a row here that no fetch will ever confirm, and the weekly full fetch_nostr
    (delete-and-recreate) drops it. That is still better than today, where such a ride is
    lost immediately — and it is the same gap dist/temporary.json exists to record.

    Never raises: the ride is already on the relay by the time we get here, so a local DB
    problem must not turn a successful publish into a 500.
    """
    if event is None:
        return
    try:
        fields = parse_post_to_ride_fields(event.to_dict())
        if fields is None or not fields.get("d"):
            return
        row = db.session.query(RideEvent).filter_by(pubkey=fields["pubkey"], d=fields["d"]).first()
        if row is None:
            db.session.add(RideEvent(**fields))
        elif fields["created_at"] >= (row.created_at or 0):
            # An edit publishes a new event id under the same (pubkey, d), so every
            # column is overwritten — including the primary key.
            for column, value in fields.items():
                setattr(row, column, value)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Could not store the published ride locally; the Nostr fetch cron will import it")
