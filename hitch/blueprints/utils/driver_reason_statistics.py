"""Count the "why did they pick you up?" answers recorded on rides."""

import json
from collections import Counter

from hitch.blueprints.utils.driver_info_choices import ALLOWED_REASONS_TO_PICK_UP


def summarise_rows(rows, hidden=frozenset()):
    """Summarise ``(d, occupants)`` rows; ``hidden`` holds d-tags of report-hidden rides."""
    counts = Counter()
    rides_read = rides_with_answer = 0
    for d, occupants in rows:
        if d in hidden:
            continue
        rides_read += 1
        try:
            people = json.loads(occupants) if isinstance(occupants, str) else occupants
        except ValueError:
            continue
        reasons = set()
        for person in people if isinstance(people, list) else []:
            if isinstance(person, dict) and person.get("was_driver"):
                raw = person.get("reasons_to_pick_up") or []
                reasons.update([raw] if isinstance(raw, str) else raw)
        reasons &= set(ALLOWED_REASONS_TO_PICK_UP)
        if reasons:
            rides_with_answer += 1
            counts.update(reasons)
    return {
        "reasons": [{"code": code, "rides": n} for code, n in counts.most_common()],
        "coverage": {"rides_read": rides_read, "rides_with_answer": rides_with_answer},
    }
