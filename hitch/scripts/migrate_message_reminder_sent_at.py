"""Migration: add `message.reminder_sent_at`.

When the "still unread after a week" reminder email covering a chat message was sent
(remind_unread_messages.py), NULL if none.

There is no migration framework in this repo and `db.create_all()` only runs at
`flask init`, so the production database has to be migrated by hand — otherwise every
request that loads a Message 500s with "no such column: message.reminder_sent_at".

Standalone script — plain python3, no app context, stdlib only, idempotent:

    sudo docker exec hitchhiking-map python3 /app/hitch/scripts/migrate_message_reminder_sent_at.py \
        --db /app/db/hitchhiking-prod.sqlite

Run it BEFORE pushing the code that depends on it: pushing to main is the deploy.
"""

import argparse
import sqlite3

COLUMN = "reminder_sent_at"


def migrate(path):
    conn = sqlite3.connect(path)
    try:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(message)")]
        if COLUMN in columns:
            print(f"message.{COLUMN} already exists — nothing to do")
            return
        with conn:
            conn.execute(f"ALTER TABLE message ADD COLUMN {COLUMN} DATETIME")
        count = conn.execute("SELECT count(*) FROM message").fetchone()[0]
        print(f"added message.{COLUMN} ({count} messages, all NULL = no reminder sent)")
    finally:
        conn.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="db/hitchhiking-prod.sqlite", help="path to the SQLite database")
    args = parser.parse_args(argv)
    migrate(args.db)


if __name__ == "__main__":
    main()
