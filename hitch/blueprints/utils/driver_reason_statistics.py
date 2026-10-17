"""Count the reasons drivers gave for stopping, as logged by the hitchhikers they picked up.

Only rides whose driver occupant carries at least one ``reasons_to_pick_up`` answer are
counted. A ride that names several reasons counts once under each, so shares are the share
of answering rides that mention a reason and do not sum to 100%.
"""

import json
from collections import Counter

from hitch.blueprints.utils.safety_statistics import _driver


def summarise_rows(rows):
    """``rows`` are ``(occupants, no_ride[, ride])`` tuples straight from ``ride_event``.

    ``ride`` (optional) carries the driver's trip purposes in ``reasons``; they are counted over
    the same answering rides as the stop reasons.
    """
    counts = Counter()
    purposes = Counter()
    answered = 0
    total = 0
    for row in rows:
        occupants, no_ride = row[0], row[1]
        ride = row[2] if len(row) > 2 else None
        total += 1
        if no_ride:
            continue
        reasons = (_driver(occupants) or {}).get("reasons_to_pick_up") or []
        if isinstance(reasons, str):
            reasons = [reasons]
        reasons = {r for r in reasons if isinstance(r, str)}
        if not reasons:
            continue
        answered += 1
        counts.update(reasons)
        if isinstance(ride, str):
            try:
                ride = json.loads(ride)
            except ValueError:
                ride = None
        trip = ride.get("reasons") if isinstance(ride, dict) else None
        if isinstance(trip, list):
            purposes.update({r for r in trip if isinstance(r, str)})
    ranked = [{"reason": code, "rides": n} for code, n in counts.most_common()]
    trips = [{"reason": code, "rides": n} for code, n in purposes.most_common()]
    return {"reasons": ranked, "trip_purposes": trips, "coverage": {"rides_total": total, "rides_answered": answered}}
