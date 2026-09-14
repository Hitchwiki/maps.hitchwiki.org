"""#202 / EXP-432: surface how people *reached* a spot.

82% of the most-opened spots already have a ride comment that says which bus,
which station, or where to walk from -- but it is only ever visible buried in the
newest-first ride-card stream. ``access_hint`` pulls the most recent comment that
names public transport or a walking approach; the spot pane (map.js ``summaryText``)
renders it verbatim under its own heading with a link to the ride it came from.

No authored prose -- it quotes an existing signed comment. The phrase list mirrors
research/spot-access-instructions-2026-09-01.md and is kept deliberately narrow (a
named mode or an explicit verb of arrival) so "the bus driver ignored me" style
comments do not match.

Split out of show.py so it can be imported and tested (show.py does all its work
at import time), same reason as spots_gpx.py / spot_naming.py.
"""

import re

ACCESS_HINT_RE = re.compile(
    r"\b("
    r"bus|tram|metro|subway|u-?bahn|s-?bahn|trolley|"
    r"train station|railway station|"
    r"walk(?:ed|ing)?|on foot|get off|got off|alight|"
    r"take the|catch the|"
    r"line \d|number \d|bus \d|route \d"
    r")\b",
    re.IGNORECASE,
)

ACCESS_HINT_MAX = 280
ACCESS_HINT_MIN_COMMENT = 15


def access_hint(spot_rides):
    """Most recent access-describing comment for a spot, as ``{"c", "id"}`` or ``None``.

    ``spot_rides`` are the per-spot ride dicts show.py writes (``comment``,
    ``submission_time``, ``id``). ``submission_time`` is compared lexically, which
    orders ISO-8601 stamps correctly.
    """
    best = None
    for r in spot_rides:
        comment = (r.get("comment") or "").strip()
        if len(comment) < ACCESS_HINT_MIN_COMMENT or not ACCESS_HINT_RE.search(comment):
            continue
        when = r.get("submission_time") or ""
        if best is None or when > best[0]:
            excerpt = comment
            if len(excerpt) > ACCESS_HINT_MAX:
                excerpt = excerpt[:ACCESS_HINT_MAX].rsplit(" ", 1)[0] + "…"
            best = (when, {"c": excerpt, "id": r["id"]})
    return best[1] if best else None
