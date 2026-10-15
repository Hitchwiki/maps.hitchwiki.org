"""Keep named Mitfahrbank benches across a night when the named-bench Overpass query failed."""

import re

BENCH_NAME = re.compile(r"^Mitfahr(er)?b(ank|änk)", re.IGNORECASE)


def carry_forward(prior, seen_ids):
    """Return prior spots that were admitted only as a named bench and are absent from tonight's fetch.

    prior: iterable of objects with .id and .tags. Real highway=hitchhiking nodes are never carried, so a spot that
    OSM deleted or retagged is still removed when its own query succeeded.
    """
    kept = []
    for spot in prior:
        tags = spot.tags or {}
        if spot.id in seen_ids or tags.get("highway") == "hitchhiking":
            continue
        if tags.get("amenity") == "bench" and BENCH_NAME.match(tags.get("name", "")):
            kept.append(spot)
    return kept
