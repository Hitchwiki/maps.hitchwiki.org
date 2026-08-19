"""Build ``dist/statistics.json`` for the public /statistics page.

Run with ``flask --app hitch generate wait_statistics``. The output is generated
outside the request path because reading every ride's JSON blobs from the production
database is work a public page must not repeat for every visitor.
"""

from datetime import datetime, timezone

from hitch.blueprints.utils.wait_time_statistics import summarise_rows
from hitch.helpers import get_db, write_json_file


def build():
    conn = get_db()
    rows = conn.execute(
        "select stops, hitchhikers, no_ride from ride_event where stops is not null and hitchhikers is not null"
    ).fetchall()
    result = summarise_rows(rows)
    result["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return result


write_json_file(build(), "statistics.json")
