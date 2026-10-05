"""Migration: add `user.current_city`, `user.current_country`, `user.current_location_updated_at`.

Where the hitchhiker is right now, shown on the profile as "Currently in …" with its age.

There is no migration framework in this repo and `db.create_all()` only runs at
`flask init`, so the production database has to be migrated by hand — otherwise every
request that loads a User 500s with "no such column: user.current_city", which is
essentially the whole logged-in site.

Standalone script — plain python3, no app context, stdlib only, idempotent:

    sudo docker exec hitchhiking-map python3 /app/hitch/scripts/migrate_current_location.py \\
        --db /app/db/hitchhiking-prod.sqlite

Run it BEFORE pushing the code that depends on it: pushing to main is the deploy.
"""

import argparse
import sqlite3

COLUMNS = [("current_country", "VARCHAR(255)"), ("current_city", "VARCHAR(255)"), ("current_location_updated_at", "DATETIME")]


def migrate(path):
    conn = sqlite3.connect(path)
    try:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(user)")}
        missing = [(name, sqltype) for name, sqltype in COLUMNS if name not in existing]
        if not missing:
            print("user current-location columns already exist — nothing to do")
            return
        with conn:
            for name, sqltype in missing:
                conn.execute(f"ALTER TABLE user ADD COLUMN {name} {sqltype}")
        print(f"added {', '.join('user.' + n for n, _ in missing)} (all NULL = not set)")
    finally:
        conn.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="db/hitchhiking-prod.sqlite", help="path to the SQLite database")
    args = parser.parse_args(argv)
    migrate(args.db)


if __name__ == "__main__":
    main()
