"""Migration: create the `feedback_note` table.

Free-text feedback a visitor leaves through the in-product prompt (see
hitch/static/feedback.js and the /feedback endpoint in main.py), replacing the
Google Form the map used to link to. There is no migration framework in this repo
and `db.create_all()` only runs at `flask init`, so the production SQLite database
has to be migrated by hand — otherwise every POST /feedback 500s with
"no such table: feedback_note".

Standalone script — plain python3, no app context, stdlib only, idempotent:

    sudo docker exec hitchhiking-map python3 /app/hitch/scripts/migrate_feedback_note.py \
        --db /app/db/hitchhiking-prod.sqlite

Run it BEFORE pushing the code that depends on it: pushing to main is the deploy,
so the new code is live a minute or two later.
"""

import argparse
import sqlite3

# Must stay in step with models.FeedbackNote. Written literally so this script needs
# neither SQLAlchemy nor the app's environment.
SCHEMA = """
CREATE TABLE feedback_note (
    id INTEGER PRIMARY KEY,
    note TEXT NOT NULL,
    context VARCHAR(64),
    page VARCHAR(255),
    user_id INTEGER REFERENCES user(id),
    username VARCHAR(255),
    email VARCHAR(255),
    ip VARCHAR(64),
    created_at DATETIME NOT NULL
)
"""


def migrate(path):
    conn = sqlite3.connect(path)
    try:
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='feedback_note'"
        ).fetchone()
        if exists:
            count = conn.execute("SELECT count(*) FROM feedback_note").fetchone()[0]
            print(f"feedback_note already exists ({count} rows) — nothing to do")
            return
        with conn:
            conn.execute(SCHEMA)
        print("created table feedback_note")
    finally:
        conn.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="db/hitchhiking-prod.sqlite", help="path to the SQLite database")
    args = parser.parse_args(argv)
    migrate(args.db)


if __name__ == "__main__":
    main()
