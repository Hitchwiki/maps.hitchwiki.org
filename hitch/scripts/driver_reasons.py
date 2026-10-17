"""Build ``dist/driver_reasons.json`` for the public /statistics/why-drivers-stop page.

Run with ``flask --app hitch generate driver_reasons``. Counts how often each "why did
they pick you up?" answer was recorded by the hitchhiker. Only reorganises answers
riders already gave; no ride-level data leaves this script.
"""

import json
from collections import Counter
from datetime import datetime, timezone

from hitch.blueprints.utils.driver_info_choices import ALLOWED_REASONS_TO_PICK_UP
from hitch.helpers import get_db, write_json_file
from hitch.scripts.hitchhiking_safety import _hidden_dtags


def build():
    conn = get_db()
    hidden = _hidden_dtags(conn)
    counts = Counter()
    rides_with_answer = 0
    rides_read = 0
    for d, occupants in conn.execute("select d, occupants from ride_event where occupants is not null"):
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
        "reasons": [{"code": code, "rides": counts[code]} for code, _ in counts.most_common()],
        "coverage": {"rides_read": rides_read, "rides_with_answer": rides_with_answer},
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


write_json_file(build(), "driver_reasons.json")
