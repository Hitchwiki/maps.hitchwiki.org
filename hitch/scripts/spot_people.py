"""#458 / EXP-579, EXP-581: how many distinct people have logged a ride at a spot.

The spot pane shows rating, wait and distance but never how many *people* stand
behind them. Counted from fields the rides already carry (``hitchhiker_name``), so
no new data and no authored prose. About 40% of rides at busy spots have no name,
so the number is a floor and the pane words it "at least N". Below
``MIN_PEOPLE_SHOWN`` it is not shown: a small number reads as thin evidence.

Split out of show.py (which does all its work at import time) so it can be tested.
"""

import zlib

MIN_PEOPLE_SHOWN = 3
_ANONYMOUS = {"", "anonymous"}


def spot_people(rides):
    """Distinct named hitchhikers across ``rides``, or None below the display floor."""
    names = set()
    for r in rides:
        name = (r.get("hitchhiker_name") or "").strip().lower()
        if name not in _ANONYMOUS:
            names.add(name)
    return len(names) if len(names) >= MIN_PEOPLE_SHOWN else None


def people_holdout(spot_id):
    """Half the qualifying spots (odd crc32 of the id) keep the line hidden, as the comparison group.

    Without it the only contrast is busy spots vs quiet ones, which differ in far more
    than the line. A crc32 of the coordinate id is stable across rebuilds (unlike ``hash()``), so a spot never flips arm.
    """
    return zlib.crc32(str(spot_id).encode()) % 2 == 1
