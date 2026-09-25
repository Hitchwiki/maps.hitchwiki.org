"""Build ``dist/hitchhiking_safety.json`` for the public /hitchhiking-safety page.

Run with ``flask --app hitch generate hitchhiking_safety`` (daily via cron). The page
answers "would the hitchhiker accept this ride again?" for a cohort the visitor
describes, so the output is one compact row per answered ride rather than an aggregate —
see hitch/blueprints/utils/safety_statistics.py for why.

Pickup countries come from the offline ``reverse_geocoder`` package in one batched call,
the same way country_ratings.py resolves rides. It is done here and never in a request:
the index costs ~30 MB of resident memory, which must not land in the long-lived waitress
workers on this OOM-prone host (the same rule /auto-trip follows).
"""

import sqlite3
from datetime import datetime, timezone

from hitch.blueprints.utils.report_ride import OWNER_DELETE_REASON, REPORTS_TO_HIDE
from hitch.blueprints.utils.safety_statistics import pickup_coords, summarise_rows
from hitch.helpers import get_db, write_json_file

# Below this, a breakdown row is marked as too thin to read anything into. Published in
# the JSON and printed on the page: it decides which numbers the page presents as
# findings, so changing it changes what the page claims.
MIN_SAMPLE = 10


def _countries(rows):
    """{ride_id: 'DE'} for every ride with a pickup coordinate.

    One batched rg.search() call, not one per ride: the package builds a KD-tree over
    every populated place on earth per call.
    """
    import reverse_geocoder as rg

    targets = []
    for row in rows:
        ride_id, stops = row[0], row[4]
        lat, lon = pickup_coords(stops)
        if lat is not None and lon is not None:
            targets.append((ride_id, (float(lat), float(lon))))
    if not targets:
        return {}
    results = rg.search([coord for _, coord in targets])
    return {ride_id: result.get("cc") for (ride_id, _), result in zip(targets, results) if result.get("cc")}


def _hidden_dtags(conn):
    """Rides hidden by community reports or deleted by their own author.

    Same rule show.py applies to every map output: REPORTS_TO_HIDE distinct reporters for
    one reason, or a single owner-deletion row. A ride its author withdrew must not keep
    voting in a published safety rate. Missing table (a DB predating the feature) means
    nothing is hidden.
    """
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
    # Every ride, not only answered ones: coverage has to be able to say how small a
    # slice of the corpus carries an answer, which is the page's first caveat.
    rows = conn.execute(
        "select id, d, hitchhikers, occupants, stops, mode_of_transportation, signals, rating, "
        "submission_time, no_ride, would_ride_again from ride_event"
    ).fetchall()
    hidden = _hidden_dtags(conn)
    if hidden:
        rows = [row for row in rows if row[1] not in hidden]
    answered = [row for row in rows if row[10] is not None]
    result = summarise_rows(rows, countries=_countries(answered))
    result["min_sample"] = MIN_SAMPLE
    result["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return result


write_json_file(build(), "hitchhiking_safety.json")
