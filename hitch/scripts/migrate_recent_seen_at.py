"""Migration: add `user.recent_seen_at`.

Epoch seconds of the last time a user opened the Activities page (/recent). The dot on
the map's Activities button compares it against RideEvent.created_at to decide whether
someone the user follows has contributed since they last looked.

There is no migration framework in this repo and `db.create_all()` only runs at
`flask init`, so the production database has to be migrated by hand — otherwise every
request that loads a User 500s with "no such column: user.recent_seen_at", which is
essentially the whole logged-in site.

Standalone script — plain python3, no app context, stdlib only, idempotent:

    sudo docker exec hitchhiking-map python3 /app/hitch/scripts/migrate_recent_seen_at.py \
        --db /app/db/hitchhiking-prod.sqlite

Run it BEFORE pushing the code that depends on it: pushing to main is the deploy, so the
new code is live a minute or two later.

NULL (the default for every existing user) means "never opened Activities", which is
exactly right — nobody has seen the feed yet.
"""

import argparse
import sqlite3

COLUMN = "recent_seen_at"


def migrate(path):
    conn = sqlite3.connect(path)
    try:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(user)")]
        if COLUMN in columns:
            print(f"user.{COLUMN} already exists — nothing to do")
            return
        with conn:
            conn.execute(f"ALTER TABLE user ADD COLUMN {COLUMN} INTEGER")
        count = conn.execute("SELECT count(*) FROM user").fetchone()[0]
        print(f"added user.{COLUMN} ({count} users, all NULL = never opened Activities)")
    finally:
        conn.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="db/hitchhiking-prod.sqlite", help="path to the SQLite database")
    args = parser.parse_args(argv)
    migrate(args.db)


if __name__ == "__main__":
    main()
