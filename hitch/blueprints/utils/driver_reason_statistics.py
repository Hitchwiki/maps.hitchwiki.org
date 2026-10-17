"""Count the reasons drivers gave for stopping, as logged by the hitchhikers they picked up.

Only rides whose driver occupant carries at least one ``reasons_to_pick_up`` answer are
counted. A ride that names several reasons counts once under each, so shares are the share
of answering rides that mention a reason and do not sum to 100%.
"""

from collections import Counter

from hitch.blueprints.utils.safety_statistics import _driver


def summarise_rows(rows):
    """``rows`` are ``(occupants, no_ride)`` tuples straight from ``ride_event``."""
    counts = Counter()
    answered = 0
    total = 0
    for occupants, no_ride in rows:
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
    ranked = [{"reason": code, "rides": n} for code, n in counts.most_common()]
    return {"reasons": ranked, "coverage": {"rides_total": total, "rides_answered": answered}}
