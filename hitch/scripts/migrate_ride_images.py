"""One-off migration: create the `ride_image` table.

Photos attached to a ride are linked to it by its Nostr `d` tag through this table (see
hitch/blueprints/utils/ride_images.py). There is no migration framework in this repo and
`db.create_all()` only runs at `flask init`, so a new table has to be created by hand on
the production database — otherwise every /ride and /ride/<d_tag> request 500s with
"no such table: ride_image".

Idempotent: safe to re-run, and it never touches an existing table. Standalone script —
plain python3, no app context, stdlib only:

    sudo docker exec hitchhiking-map python3 /app/hitch/scripts/migrate_ride_images.py \
        --db /app/db/hitchhiking-prod.sqlite

Run it BEFORE pushing the code that depends on it: pushing to main is the deploy, so the
new code is live a minute or two later.
"""

import argparse
import sqlite3

# Must stay in step with models.RideImage. Written literally rather than generated from
# the model so this script needs neither SQLAlchemy nor the app's environment.
SCHEMA = """
CREATE TABLE ride_image (
    id INTEGER PRIMARY KEY,
    ride_d_tag VARCHAR(255) NOT NULL,
    filename VARCHAR(255) NOT NULL UNIQUE,
    user_id INTEGER REFERENCES user(id),
    width INTEGER,
    height INTEGER,
    created_at DATETIME NOT NULL
)
"""

# Every read of this table is "the photos of one ride", so the d tag carries the index.
INDEX = "CREATE INDEX ix_ride_image_ride_d_tag ON ride_image (ride_d_tag)"


def migrate(path):
    conn = sqlite3.connect(path)
    try:
        exists = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ride_image'").fetchone()
        if exists:
            count = conn.execute("SELECT count(*) FROM ride_image").fetchone()[0]
            print(f"ride_image already exists ({count} rows) — nothing to do")
            return
        with conn:
            conn.execute(SCHEMA)
            conn.execute(INDEX)
        print("created table ride_image")
    finally:
        conn.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="db/hitchhiking-prod.sqlite", help="path to the SQLite database")
    args = parser.parse_args(argv)
    migrate(args.db)


if __name__ == "__main__":
    main()
