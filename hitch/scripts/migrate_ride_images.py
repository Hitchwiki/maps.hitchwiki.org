"""Migration: create / update the `ride_image` table.

Photos attached to a ride are linked to it by its Nostr `d` tag through this table (see
hitch/blueprints/utils/ride_images.py). There is no migration framework in this repo and
`db.create_all()` only runs at `flask init`, so the production SQLite database has to be
migrated by hand — otherwise every /ride and /ride/<d_tag> request 500s with
"no such table: ride_image".

Two steps, both idempotent, both handled here:

1. Create the table if it does not exist.
2. Bring an existing table up to the draft-upload schema: `ride_d_tag` must become
   NULLable and a `draft_token` column has to appear. Photos are uploaded the moment the
   user picks one — before the ride, and therefore its `d` tag, exists — so a freshly
   uploaded row has no ride to point at yet. SQLite has no `ALTER TABLE ... ALTER
   COLUMN`, so relaxing the NOT NULL means the twelve-step rebuild: new table, copy the
   rows, drop the old one, rename.

Standalone script — plain python3, no app context, stdlib only:

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
CREATE TABLE {name} (
    id INTEGER PRIMARY KEY,
    ride_d_tag VARCHAR(255),
    draft_token VARCHAR(64),
    filename VARCHAR(255) NOT NULL UNIQUE,
    user_id INTEGER REFERENCES user(id),
    width INTEGER,
    height INTEGER,
    created_at DATETIME NOT NULL
)
"""

# Every read of this table is either "the photos of one ride" or "the photos of one
# unsubmitted form", so both keys carry an index.
INDEXES = [
    "CREATE INDEX ix_ride_image_ride_d_tag ON ride_image (ride_d_tag)",
    "CREATE INDEX ix_ride_image_draft_token ON ride_image (draft_token)",
]

# Columns carried over from the pre-draft schema. draft_token is new, so it is not here.
CARRIED_COLUMNS = ["id", "ride_d_tag", "filename", "user_id", "width", "height", "created_at"]


def columns(conn, table):
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def create(conn):
    with conn:
        conn.execute(SCHEMA.format(name="ride_image"))
        for statement in INDEXES:
            conn.execute(statement)
    print("created table ride_image")


def rebuild(conn):
    """Twelve-step rebuild: adds draft_token and drops the NOT NULL on ride_d_tag."""
    before = conn.execute("SELECT count(*) FROM ride_image").fetchone()[0]
    carried = ", ".join(CARRIED_COLUMNS)

    # foreign_keys must be off around a table rebuild, and toggling it inside a
    # transaction is a silent no-op — hence outside the BEGIN.
    conn.execute("PRAGMA foreign_keys=OFF")
    with conn:
        conn.execute(SCHEMA.format(name="ride_image_migrated"))
        conn.execute(f"INSERT INTO ride_image_migrated ({carried}) SELECT {carried} FROM ride_image")
        conn.execute("DROP TABLE ride_image")
        conn.execute("ALTER TABLE ride_image_migrated RENAME TO ride_image")
        for statement in INDEXES:
            conn.execute(statement)
    conn.execute("PRAGMA foreign_keys=ON")

    after = conn.execute("SELECT count(*) FROM ride_image").fetchone()[0]
    # A row count that moved means the copy lost or duplicated photos; say so loudly
    # rather than leaving someone to find a ride page with missing pictures.
    if before != after:
        raise SystemExit(f"row count changed during migration: {before} -> {after}")
    print(f"ride_image rebuilt with draft_token and a nullable ride_d_tag ({after} photos preserved)")


def migrate(path):
    conn = sqlite3.connect(path)
    try:
        exists = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ride_image'").fetchone()
        if not exists:
            create(conn)
            return
        cols = columns(conn, "ride_image")
        if "draft_token" in cols:
            count = conn.execute("SELECT count(*) FROM ride_image").fetchone()[0]
            print(f"ride_image is already up to date ({count} rows) — nothing to do")
            return
        if sorted(cols) != sorted(CARRIED_COLUMNS):
            raise SystemExit(f"unexpected ride_image columns {cols}; expected {CARRIED_COLUMNS} — migrate by hand")
        rebuild(conn)
    finally:
        conn.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="db/hitchhiking-prod.sqlite", help="path to the SQLite database")
    args = parser.parse_args(argv)
    migrate(args.db)


if __name__ == "__main__":
    main()
