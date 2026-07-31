"""Migration: index `ride_event.d`.

`d` is the addressable id of a ride (the Nostr `d` tag), and it is how every profile-side
view resolves one: /ride/<d_tag>, trip membership (`trip_ride.ride_d_tag`), co-hitchhiker
invitations, save-trip's ownership check. The column had no index, so each of those
lookups was a full scan of a 79k-row table whose rows carry several JSON blobs — ~0.3 s
apiece measured on prod.

That is invisible for a single lookup and brutal in a loop: /account/Ecureuil spent 19 s
of its 22 s resolving the 64 member rides of one trip, one query at a time.

There is no migration framework in this repo and `db.create_all()` only runs at
`flask init`, so the index has to be created by hand on the production database — the
`index=True` added to models.RideEvent.d only affects a database built from scratch.

Standalone script — plain python3, no app context, stdlib only, idempotent:

    sudo docker exec hitchhiking-map python3 /app/hitch/scripts/migrate_ride_event_d_index.py \
        --db /app/db/hitchhiking-prod.sqlite

Safe to run against the live database: CREATE INDEX takes a write lock for the seconds it
needs to build (~79k rows), and readers are unaffected under WAL.
"""

import argparse
import sqlite3
import time

# Name matches what SQLAlchemy would emit for `index=True` on RideEvent.d, so a database
# created by `flask init` and one migrated by this script end up with the same schema.
INDEX_NAME = "ix_ride_event_d"
INDEX_SQL = f"CREATE INDEX {INDEX_NAME} ON ride_event (d)"


def migrate(path):
    conn = sqlite3.connect(path)
    try:
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
            (INDEX_NAME,),
        ).fetchone()
        if exists:
            print(f"{INDEX_NAME} already exists — nothing to do")
            return

        rows = conn.execute("SELECT count(*) FROM ride_event").fetchone()[0]
        started = time.time()
        with conn:
            conn.execute(INDEX_SQL)
        print(f"created {INDEX_NAME} over {rows} rides in {time.time() - started:.1f}s")

        # Confirm the planner actually uses it; an index the queries ignore is worse than
        # none (it costs writes and buys nothing), and that would be silent otherwise.
        plan = conn.execute("EXPLAIN QUERY PLAN SELECT * FROM ride_event WHERE d = 'x'").fetchall()
        detail = " | ".join(str(row[-1]) for row in plan)
        if INDEX_NAME not in detail:
            raise SystemExit(f"index created but the planner still does not use it: {detail}")
        print(f"query plan: {detail}")
    finally:
        conn.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="db/hitchhiking-prod.sqlite", help="path to the SQLite database")
    args = parser.parse_args(argv)
    migrate(args.db)


if __name__ == "__main__":
    main()
