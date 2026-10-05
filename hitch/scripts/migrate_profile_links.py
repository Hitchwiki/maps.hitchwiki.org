"""Migration: add `user.profile_links`.

Up to 5 links to the user's profiles elsewhere, a JSON list of URLs (hitch/profile_links.py).

There is no migration framework in this repo and `db.create_all()` only runs at
`flask init`, so the production database has to be migrated by hand — otherwise every
request that loads a User 500s with "no such column: user.profile_links", which is
essentially the whole logged-in site.

Standalone script — plain python3, no app context, stdlib only, idempotent:

    sudo docker exec hitchhiking-map python3 /app/hitch/scripts/migrate_profile_links.py \\
        --db /app/db/hitchhiking-prod.sqlite

Run it BEFORE pushing the code that depends on it: pushing to main is the deploy.
"""

import argparse
import sqlite3

COLUMN = "profile_links"


def migrate(path):
    conn = sqlite3.connect(path)
    try:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(user)")]
        if COLUMN in columns:
            print(f"user.{COLUMN} already exists — nothing to do")
            return
        with conn:
            conn.execute(f"ALTER TABLE user ADD COLUMN {COLUMN} TEXT")
        count = conn.execute("SELECT count(*) FROM user").fetchone()[0]
        print(f"added user.{COLUMN} ({count} users, all NULL = no links)")
    finally:
        conn.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="db/hitchhiking-prod.sqlite", help="path to the SQLite database")
    args = parser.parse_args(argv)
    migrate(args.db)


if __name__ == "__main__":
    main()
