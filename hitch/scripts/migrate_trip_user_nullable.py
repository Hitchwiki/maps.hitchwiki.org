"""One-off migration: drop the NOT NULL on trip.user_id.

Auto-generated trips (see /auto-trip in user.py) also exist for journeys logged
anonymously through the in-ride tracker, and those have no account to hang off — so
trip.user_id has to accept NULL.

SQLite cannot relax a column constraint in place: there is no
`ALTER TABLE ... ALTER COLUMN`, so the only supported route is the twelve-step
rebuild (new table → copy → drop → rename). The trip table is tiny (tens of rows,
no indexes, no triggers), which is why doing it inline here is safe.

Standalone script — plain python3, no app context, stdlib only:

    sudo python3 hitch/scripts/migrate_trip_user_nullable.py --db db/hitchhiking-prod.sqlite
"""

import argparse
import sqlite3
import sys

# The post-migration schema. Kept literal rather than derived from the old CREATE
# statement: a regex over DDL is exactly the kind of clever that silently drops a
# column. Must stay in step with models.Trip.
NEW_SCHEMA = """
CREATE TABLE trip_migrated (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    name VARCHAR(255) NOT NULL,
    created_at DATETIME NOT NULL,
    description TEXT
)
"""

COLUMNS = ["id", "user_id", "name", "created_at", "description"]


def user_id_is_nullable(conn):
    """True when trip.user_id already accepts NULL (migration is a no-op)."""
    for row in conn.execute("PRAGMA table_info(trip)"):
        if row[1] == "user_id":
            return row[3] == 0  # notnull flag
    raise SystemExit("trip table has no user_id column — refusing to guess")


def migrate(path):
    conn = sqlite3.connect(path)
    try:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(trip)")]
        if cols != COLUMNS:
            raise SystemExit(f"unexpected trip columns {cols}; expected {COLUMNS} — migrate by hand")
        if user_id_is_nullable(conn):
            print("trip.user_id is already nullable — nothing to do")
            return
        before = conn.execute("SELECT count(*) FROM trip").fetchone()[0]

        # foreign_keys must be off around a table rebuild, and toggling it inside a
        # transaction is a silent no-op — hence outside the BEGIN.
        conn.execute("PRAGMA foreign_keys=OFF")
        with conn:
            conn.execute(NEW_SCHEMA)
            conn.execute(f"INSERT INTO trip_migrated ({', '.join(COLUMNS)}) SELECT {', '.join(COLUMNS)} FROM trip")
            conn.execute("DROP TABLE trip")
            conn.execute("ALTER TABLE trip_migrated RENAME TO trip")
        conn.execute("PRAGMA foreign_keys=ON")

        after = conn.execute("SELECT count(*) FROM trip").fetchone()[0]
        # A row count that moved means the copy lost or duplicated trips; say so loudly
        # rather than leaving someone to discover it from a missing trip page.
        if before != after:
            raise SystemExit(f"row count changed during migration: {before} -> {after}")
        print(f"trip.user_id is now nullable ({after} trips preserved)")
    finally:
        conn.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="db/hitchhiking-prod.sqlite", help="path to the SQLite database")
    args = parser.parse_args(argv)
    migrate(args.db)


if __name__ == "__main__":
    sys.exit(main())
