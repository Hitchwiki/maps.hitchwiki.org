"""Build ``dist/driver_reason_statistics.json`` for the public /statistics/driver-reasons page.

Run with ``flask --app hitch generate driver_reason_statistics``. Reads the ride table, so it
stays out of the request path like the other statistics generators.
"""

import sqlite3
from datetime import datetime, timezone

from hitch.blueprints.utils.driver_reason_statistics import summarise_rows
from hitch.blueprints.utils.report_ride import OWNER_DELETE_REASON, REPORTS_TO_HIDE
from hitch.helpers import get_db, write_json_file


def _hidden_dtags(conn):
    """Rides hidden by community reports or deleted by their author (same rule as show.py)."""
    try:
        rows = conn.execute(
            "select ride_d_tag from ride_report group by ride_d_tag, reason "
            f"having count(*) >= {REPORTS_TO_HIDE} or reason = '{OWNER_DELETE_REASON}'"
        ).fetchall()
    except sqlite3.Error:
        return set()
    return {row[0] for row in rows}


def build():
    conn = get_db()
    rows = conn.execute("select d, occupants, no_ride, ride from ride_event where occupants is not null").fetchall()
    hidden = _hidden_dtags(conn)
    result = summarise_rows([(r[1], r[2], r[3]) for r in rows if r[0] not in hidden])
    result["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return result


write_json_file(build(), "driver_reason_statistics.json")
