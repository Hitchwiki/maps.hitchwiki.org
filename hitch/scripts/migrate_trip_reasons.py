"""Migration: add `trip.reasons_to_hitchhike`.

Comma-separated ReasonToHitchhikeEnum codes the trip builder now asks for ("Why are you
hitchhiking?"), the same vocabulary and storage shape the /ride form uses. Saving a trip
adds them to every ride in it by union; this column is what the picker shows when the
trip is reopened.

There is no migration framework in this repo and `db.create_all()` only runs at
`flask init`, so the production database has to be migrated by hand — otherwise every
query touching Trip 500s with "no such column: trip.reasons_to_hitchhike", which is
/me, every profile, every trip page and the map's trip links.

Standalone script — plain python3, no app context, stdlib only, idempotent:

    sudo docker exec hitchhiking-map python3 /app/hitch/scripts/migrate_trip_reasons.py \
        --db /app/db/hitchhiking-prod.sqlite

Run it BEFORE pushing the code that depends on it: pushing to main is the deploy, so the
new code is live a minute or two later.

NULL (the default for every existing trip) means "no reasons stated", which is exactly
right — nobody has been asked yet.
"""

import argparse
import sqlite3

COLUMN = "reasons_to_hitchhike"


def migrate(path):
    conn = sqlite3.connect(path)
    try:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(trip)")]
        if COLUMN in columns:
            print(f"trip.{COLUMN} already exists — nothing to do")
            return
        with conn:
            conn.execute(f"ALTER TABLE trip ADD COLUMN {COLUMN} VARCHAR(255)")
        count = conn.execute("SELECT count(*) FROM trip").fetchone()[0]
        print(f"added trip.{COLUMN} ({count} trips, all NULL = no reasons stated yet)")
    finally:
        conn.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="db/hitchhiking-prod.sqlite", help="path to the SQLite database")
    args = parser.parse_args(argv)
    migrate(args.db)


if __name__ == "__main__":
    main()
