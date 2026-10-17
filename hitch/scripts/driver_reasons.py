"""Build ``dist/driver_reasons.json`` for the public /statistics/why-drivers-stop page.

Run with ``flask --app hitch generate driver_reasons``. Counts how often each "why did
they pick you up?" answer was recorded by the hitchhiker. Only reorganises answers
riders already gave; no ride-level data leaves this script.
"""

from datetime import datetime, timezone

from hitch.blueprints.utils.driver_reason_statistics import summarise_rows
from hitch.helpers import get_db, write_json_file
from hitch.scripts.hitchhiking_safety import _hidden_dtags


def build():
    conn = get_db()
    rows = conn.execute("select d, occupants from ride_event where occupants is not null").fetchall()
    result = summarise_rows(rows, _hidden_dtags(conn))
    result["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return result


write_json_file(build(), "driver_reasons.json")
