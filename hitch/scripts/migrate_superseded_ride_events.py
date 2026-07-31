"""Migration: create the `superseded_ride_event` table.

When a user edits or claims a ride that came in through one of the bulk imports, the
rewrite is signed with this app's *current* Nostr key while the original was signed with an
older one. Kind 36820 is addressable per (pubkey, kind, d), so the rewrite does not replace
the original — it sits next to it on the relays, and we cannot delete it (NIP-09 honours
only a deletion signed by the author, whose nsec we no longer publish with).

This table lists those retired coordinates so `fetch_nostr` and `fetch_nostr_incremental`
skip them; without it the weekly full re-fetch re-imports the pre-edit copy and the ride
shows twice on the map. See models.SupersededRideEvent.

There is no migration framework in this repo and `db.create_all()` only runs at
`flask init`, so the production database has to be migrated by hand — otherwise every ride
edit and every fetch run 500s / crashes with "no such table: superseded_ride_event".

Standalone script — plain python3, no app context, stdlib only, idempotent:

    sudo docker exec hitchhiking-map python3 \
        /app/hitch/scripts/migrate_superseded_ride_events.py --db /app/db/hitchhiking-prod.sqlite

Run it BEFORE pushing the code that depends on it: pushing to main is the deploy, so the
new code is live a minute or two later.
"""

import argparse
import sqlite3

# Must stay in step with models.SupersededRideEvent. Written literally rather than
# generated from the model so this script needs neither SQLAlchemy nor the app's
# environment.
SCHEMA = """
CREATE TABLE superseded_ride_event (
    pubkey VARCHAR(64) NOT NULL,
    d VARCHAR(255) NOT NULL,
    superseded_at INTEGER,
    PRIMARY KEY (pubkey, d)
)
"""


def migrate(path):
    conn = sqlite3.connect(path)
    try:
        exists = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='superseded_ride_event'").fetchone()
        if exists:
            count = conn.execute("SELECT count(*) FROM superseded_ride_event").fetchone()[0]
            print(f"superseded_ride_event already exists ({count} rows) — nothing to do")
            return
        with conn:
            conn.execute(SCHEMA)
        print("created table superseded_ride_event")
    finally:
        conn.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="db/hitchhiking-prod.sqlite", help="path to the SQLite database")
    args = parser.parse_args(argv)
    migrate(args.db)


if __name__ == "__main__":
    main()
