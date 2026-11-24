"""Append-only CSV of anonymous 👍/👎 votes (+ optional text) on planner results.

Written by `/log-route-feedback`. No user id or IP is stored; coordinates are rounded to
3 decimals by the client. Lives in `logs/` so it is not served publicly.
"""

import csv
import os
from datetime import datetime, timezone

from hitch.helpers import dirs

ROUTE_FEEDBACK_LOG_PATH = os.path.join(dirs["root"], "logs", "route_feedback.csv")
# Till 2026-11-23: the second ask ("is this route easy to understand?") is about how the result is shown, not the
# route itself, so it gets its own file: mixing them would make a 👎 on the layout look like a bad route.
ROUTE_PRESENTATION_FEEDBACK_LOG_PATH = os.path.join(dirs["root"], "logs", "route_presentation_feedback.csv")

_HEADER = ["timestamp", "start_lat", "start_lon", "dest_lat", "dest_lon", "vote", "text", "auto"]


def log_route_feedback(start_lat, start_lon, dest_lat, dest_lon, vote, text="", auto=0, aspect="route"):
    """Record one vote. Never raises: logging must not break the beacon request."""
    # Module attributes are read at call time so tests can monkeypatch either path.
    path = ROUTE_PRESENTATION_FEEDBACK_LOG_PATH if aspect == "presentation" else ROUTE_FEEDBACK_LOG_PATH
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        write_header = not os.path.exists(path) or os.path.getsize(path) == 0
        with open(path, "a", newline="", encoding="utf-8") as f:
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
                    1 if auto else 0,
                ]
            )
    except Exception:
        from flask import current_app

        current_app.logger.exception("Failed to log route feedback")


# Till 2026-11-24: structured labels for the routing eval. One row per tap: where it came from (the result's 👎
# reasons, or the after-trip ask), the answer, and a fixed reason code. Own file, so the 👍/👎 counts above stay as
# they were.
ROUTE_LABEL_LOG_PATH = os.path.join(dirs["root"], "logs", "route_labels.csv")
LABEL_SOURCES = ("result", "trip")
LABEL_ANSWERS = ("up", "partly", "down")
LABEL_REASONS = ("", "first_spot", "walking", "detour", "spot_bad", "elsewhere", "other", "text")
_LABEL_HEADER = ["timestamp", "start_lat", "start_lon", "dest_lat", "dest_lon", "source", "answer", "reason", "text", "auto"]


def log_route_label(start_lat, start_lon, dest_lat, dest_lon, source, answer, reason="", text="", auto=0):
    """Record one label. Returns False for values outside the fixed sets. Never raises."""
    if source not in LABEL_SOURCES or answer not in LABEL_ANSWERS or reason not in LABEL_REASONS:
        return False
    path = ROUTE_LABEL_LOG_PATH
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        write_header = not os.path.exists(path) or os.path.getsize(path) == 0
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(_LABEL_HEADER)
            writer.writerow(
                [
                    datetime.now(timezone.utc).isoformat(),
                    f"{start_lat:.3f}",
                    f"{start_lon:.3f}",
                    f"{dest_lat:.3f}",
                    f"{dest_lon:.3f}",
                    source,
                    answer,
                    reason,
                    " ".join((text or "").split())[:300],
                    1 if auto else 0,
                ]
            )
        return True
    except Exception:
        from flask import current_app

        current_app.logger.exception("Failed to log route label")
        return False
