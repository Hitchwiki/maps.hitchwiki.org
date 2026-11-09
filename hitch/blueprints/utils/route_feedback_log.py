"""Append-only CSV of anonymous 👍/👎 votes (+ optional text) on planner results.

Written by `/log-route-feedback`. No user id or IP is stored; coordinates are rounded to
3 decimals by the client. Lives in `logs/` so it is not served publicly.
"""

import csv
import os
from datetime import datetime, timezone

from hitch.helpers import dirs

ROUTE_FEEDBACK_LOG_PATH = os.path.join(dirs["root"], "logs", "route_feedback.csv")

_HEADER = ["timestamp", "start_lat", "start_lon", "dest_lat", "dest_lon", "vote", "text"]


def log_route_feedback(start_lat, start_lon, dest_lat, dest_lon, vote, text=""):
    """Record one vote. Never raises: logging must not break the beacon request."""
    try:
        os.makedirs(os.path.dirname(ROUTE_FEEDBACK_LOG_PATH), exist_ok=True)
        write_header = not os.path.exists(ROUTE_FEEDBACK_LOG_PATH) or os.path.getsize(ROUTE_FEEDBACK_LOG_PATH) == 0
        with open(ROUTE_FEEDBACK_LOG_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(_HEADER)
            writer.writerow(
                [
                    datetime.now(timezone.utc).isoformat(),
                    f"{start_lat:.3f}",
                    f"{start_lon:.3f}",
                    f"{dest_lat:.3f}",
                    f"{dest_lon:.3f}",
                    vote,
                    " ".join((text or "").split())[:300],
                ]
            )
    except Exception:
        from flask import current_app

        current_app.logger.exception("Failed to log route feedback")
