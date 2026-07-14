"""Append-only CSV of every route the in-app planner is asked to compute.

Route planning happens entirely client-side (`static/routing.js`), so the server
never sees which routes people look for unless the client tells it. `routing.js`
fires a `navigator.sendBeacon` at `/log-route-request` each time a search runs;
this records a timestamp plus the start and destination coordinates so we can see
what corridors are in demand.

Lives in `logs/` rather than `dist/` because `dist/` is served publicly by the
catch-all route — request logs should not be reachable over HTTP.
"""

import csv
import os
from datetime import datetime, timezone

from hitch.helpers import dirs

ROUTE_REQUEST_LOG_PATH = os.path.join(dirs["root"], "logs", "route_requests.csv")

_HEADER = ["timestamp", "start_lat", "start_lon", "dest_lat", "dest_lon"]


def log_route_request(start_lat, start_lon, dest_lat, dest_lon):
    """Record one requested route. Never raises: logging must not break the
    (fire-and-forget) beacon request."""
    try:
        os.makedirs(os.path.dirname(ROUTE_REQUEST_LOG_PATH), exist_ok=True)
        write_header = not os.path.exists(ROUTE_REQUEST_LOG_PATH) or os.path.getsize(ROUTE_REQUEST_LOG_PATH) == 0
        with open(ROUTE_REQUEST_LOG_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(_HEADER)
            writer.writerow(
                [
                    datetime.now(timezone.utc).isoformat(),
                    f"{start_lat:.5f}",
                    f"{start_lon:.5f}",
                    f"{dest_lat:.5f}",
                    f"{dest_lon:.5f}",
                ]
            )
    except Exception:
        from flask import current_app

        current_app.logger.exception("Failed to log route request")
