"""Spots worth listing in the sitemap (#1048)."""

import json
import os
import re

# Same pattern as main.SPOT_ID_RE; duplicated so scripts need not import the blueprint.
SPOT_ID_RE = re.compile(r"^-?\d+\.\d{1,7}_-?\d+\.\d{1,7}$")
SPOT_SITEMAP_MIN_RIDES = 5


def sitemap_spot_ids(by_spot_dir, min_rides=SPOT_SITEMAP_MIN_RIDES):
    """Ids of spots with >= min_rides rated rides, sorted.

    Rated spots are the ones render_spot serves indexable (a description exists only
    when a rating does), so no listed URL is noindex.
    """
    try:
        names = os.listdir(by_spot_dir)
    except OSError:
        return []
    ids = []
    for name in names:
        spot_id, ext = os.path.splitext(name)
        if ext != ".json" or not SPOT_ID_RE.match(spot_id):
            continue
        try:
            with open(os.path.join(by_spot_dir, name), encoding="utf-8") as f:
                rides = json.load(f).get("rides") or []
        except (OSError, ValueError):
            continue
        if sum(1 for r in rides if r.get("rating")) >= min_rides:
            ids.append(spot_id)
    return sorted(ids)
