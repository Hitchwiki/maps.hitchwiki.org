"""Append-only CSV of free-text feedback notes left through the in-app widget.

The widget (feedback_widget() macro, wired by setupMapFeedback() in map.js)
replaced a Google Form that got 0 responses ever. A note also rides an analytics
event, but ad-blockers drop the tracker and it cannot see who is signed in — this
file is the durable record, and the one place the logged-in username (or the
optional reply email an anonymous visitor typed) is attached.

`username` is filled server-side from the session, never from the client. `email`
is only ever what a signed-out visitor volunteered for a reply — stored here in
`logs/`, not in the database or its off-site backups, and not tied to any ride.

Lives in `logs/` rather than `dist/` because `dist/` is served publicly by the
catch-all route.
"""

import csv
import os
from datetime import datetime, timezone

from hitch.helpers import dirs

FEEDBACK_LOG_PATH = os.path.join(dirs["root"], "logs", "feedback.csv")

_HEADER = ["timestamp", "source", "username", "email", "text"]

# The client is untrusted; only notes tagged with a placement we render are kept.
# The ambient popup passes "ambient-<trigger>", so that family is matched by prefix.
KNOWN_SOURCES = {"success-overlay", "signup-prompt"}


def is_known_source(source):
    return source in KNOWN_SOURCES or (isinstance(source, str) and source.startswith("ambient-"))


def log_feedback(source, username, email, text):
    """Record one feedback note. Never raises: this is a fire-and-forget beacon."""
    try:
        os.makedirs(os.path.dirname(FEEDBACK_LOG_PATH), exist_ok=True)
        write_header = not os.path.exists(FEEDBACK_LOG_PATH) or os.path.getsize(FEEDBACK_LOG_PATH) == 0
        with open(FEEDBACK_LOG_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(_HEADER)
            writer.writerow(
                [
                    datetime.now(timezone.utc).isoformat(),
                    source,
                    username or "",
                    email or "",
                    (text or "").replace("\r\n", "\n"),
                ]
            )
    except Exception:
        from flask import current_app

        current_app.logger.exception("Failed to log feedback from %s", source)
