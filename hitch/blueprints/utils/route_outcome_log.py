"""Append-only CSV of planner outcomes (found / none), independent of Umami.

Written by `/log-route-outcome`. No coordinates, user id or IP: only the outcome, which
graph answered, the option count and the no-route reason. Lives in `logs/` (not public).
"""

import csv
import os
from datetime import datetime, timezone

from hitch.helpers import dirs

ROUTE_OUTCOME_LOG_PATH = os.path.join(dirs["root"], "logs", "route_outcomes.csv")

_HEADER = ["timestamp", "outcome", "graph", "options", "reason", "auto"]
OUTCOMES = ("found", "none")


def log_route_outcome(outcome, graph="", options=0, reason="", auto=0):
    """Record one planner outcome. Never raises: logging must not break the beacon request."""
    try:
        os.makedirs(os.path.dirname(ROUTE_OUTCOME_LOG_PATH), exist_ok=True)
        write_header = not os.path.exists(ROUTE_OUTCOME_LOG_PATH) or os.path.getsize(ROUTE_OUTCOME_LOG_PATH) == 0
        with open(ROUTE_OUTCOME_LOG_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(_HEADER)
            writer.writerow(
                [
                    datetime.now(timezone.utc).isoformat(),
                    outcome,
                    str(graph)[:20],
                    int(options),
                    str(reason)[:40],
                    1 if auto else 0,
                ]
            )
    except Exception:
        from flask import current_app

        current_app.logger.exception("Failed to log route outcome")
