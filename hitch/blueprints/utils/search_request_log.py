"""Append-only CSV of every place picked from the map's search bar.

The search bar is a client-side Leaflet geocoder (Photon), so the server never
sees which places people look up unless the client tells it. `map.js` fires a
`navigator.sendBeacon` at `/log-search-request` when a result is selected; this
records a timestamp, the chosen place name, and its coordinates.

Lives in `logs/` rather than `dist/` because `dist/` is served publicly by the
catch-all route — request logs should not be reachable over HTTP.
"""

import csv
import os
from datetime import datetime, timezone

from hitch.helpers import dirs

SEARCH_REQUEST_LOG_PATH = os.path.join(dirs["root"], "logs", "search_requests.csv")

_HEADER = ["timestamp", "name", "lat", "lon"]


def log_search_request(name, lat, lon):
    """Record one selected search result. Never raises: logging must not break
    the (fire-and-forget) beacon request."""
    try:
        os.makedirs(os.path.dirname(SEARCH_REQUEST_LOG_PATH), exist_ok=True)
        write_header = not os.path.exists(SEARCH_REQUEST_LOG_PATH) or os.path.getsize(SEARCH_REQUEST_LOG_PATH) == 0
        with open(SEARCH_REQUEST_LOG_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(_HEADER)
            writer.writerow(
                [
                    datetime.now(timezone.utc).isoformat(),
                    (name or "")[:200],
                    f"{lat:.5f}",
                    f"{lon:.5f}",
                ]
            )
    except Exception:
        from flask import current_app

        current_app.logger.exception("Failed to log search request")
