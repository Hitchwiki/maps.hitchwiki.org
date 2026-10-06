"""Per-country "would you ride again?" counts for the city pages (IDEAS #640).

Reads dist/hitchhiking_safety.json (one compact row per answered ride, ``cc`` = ISO-2
pickup country, ``w`` = 1 if the hitchhiker would ride again). Counts only; a country
under MIN_ANSWERS answers is dropped so a thin sample never reads as a finding. Any
failure returns {}: cities.py also writes sitemap.xml and robots.txt, so this must never raise.
"""

import json
import os

MIN_ANSWERS = 10


def counts_by_country(data, min_answers=MIN_ANSWERS):
    """{'DE': {'yes': 41, 'total': 44}} for countries with >= min_answers answers."""
    totals = {}
    for row in (data or {}).get("rides") or []:
        cc = row.get("cc")
        if not cc:
            continue
        entry = totals.setdefault(cc, {"yes": 0, "total": 0})
        entry["total"] += 1
        entry["yes"] += 1 if row.get("w") else 0
    return {cc: v for cc, v in totals.items() if v["total"] >= min_answers}


def load_counts(dist_dir):
    try:
        with open(os.path.join(dist_dir, "hitchhiking_safety.json"), encoding="utf-8") as f:
            return counts_by_country(json.load(f))
    except Exception:
        return {}
