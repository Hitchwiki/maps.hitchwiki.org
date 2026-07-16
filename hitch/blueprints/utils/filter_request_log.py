"""Append-only CSV of every filter combination applied on the map.

Filtering runs entirely client-side (`applyParams` in `map.js` reads the query
params and hides markers), so the server never sees which filters people reach
for. `map.js` fires a debounced `navigator.sendBeacon` at `/log-filter-request`
once a filter set settles; this records a timestamp, the value of every filter,
and how many spots survived.

`matches` is what makes the log answer "which filters are *useful*" rather than
just "which are used": a filter that repeatedly lands on 0 spots is one people
try and abandon.

Lives in `logs/` rather than `dist/` because `dist/` is served publicly by the
catch-all route — request logs should not be reachable over HTTP.
"""

import csv
import os
from datetime import datetime, timezone

from hitch.helpers import dirs

FILTER_REQUEST_LOG_PATH = os.path.join(dirs["root"], "logs", "filter_requests.csv")

# Order is the CSV column order and must stay stable — the file is append-only,
# so a reordering would silently misalign every row written before it.
FILTER_FIELDS = [
    "recent",
    "osmonly",
    "carpoolingonly",
    "fuelonly",
    "hitchwikionly",
    "user",
    "text",
    "mindistance",
    "minrides",
    "minrating",
    "vehicle",
    "method",
    "mindate",
    "maxdate",
]

_HEADER = ["timestamp"] + FILTER_FIELDS + ["matches"]


def log_filter_request(filters, matches):
    """Record one settled filter combination. Never raises: logging must not
    break the (fire-and-forget) beacon request."""
    try:
        os.makedirs(os.path.dirname(FILTER_REQUEST_LOG_PATH), exist_ok=True)
        write_header = not os.path.exists(FILTER_REQUEST_LOG_PATH) or os.path.getsize(FILTER_REQUEST_LOG_PATH) == 0
        with open(FILTER_REQUEST_LOG_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(_HEADER)
            row = [datetime.now(timezone.utc).isoformat()]
            # Free-text filters are user input; cap them so one long paste can't
            # bloat the log or break the row.
            row += [str(filters.get(k, ""))[:100] for k in FILTER_FIELDS]
            row.append("" if matches is None else matches)
            writer.writerow(row)
    except Exception:
        from flask import current_app

        current_app.logger.exception("Failed to log filter request")
