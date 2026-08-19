"""Aggregate waiting times by hitchhiker group size and gender composition."""

import json
import re
from collections import defaultdict
from itertools import combinations_with_replacement
from statistics import median

KNOWN_GENDERS = ("female", "male", "non_binary", "prefer_not_to_say")
GENDER_ORDER = (*KNOWN_GENDERS, "unknown")
WAIT_RE = re.compile(r"^PT(\d+)M$")


def _json_value(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return None
    return value


def _wait_minutes(stops):
    stops = _json_value(stops)
    if not isinstance(stops, list) or not stops or not isinstance(stops[0], dict):
        return None
    match = WAIT_RE.fullmatch(stops[0].get("waiting_duration") or "")
    return int(match.group(1)) if match else None


def _composition(hitchhikers):
    hitchhikers = _json_value(hitchhikers)
    if not isinstance(hitchhikers, list) or not 1 <= len(hitchhikers) <= 4:
        return None
    counts = {gender: 0 for gender in GENDER_ORDER}
    for hitchhiker in hitchhikers:
        gender = hitchhiker.get("gender") if isinstance(hitchhiker, dict) else None
        counts[gender if gender in KNOWN_GENDERS else "unknown"] += 1
    return tuple(counts[gender] for gender in GENDER_ORDER)


def _median(values):
    value = float(median(values))
    return int(value) if value.is_integer() else round(value, 1)


def summarise_rows(rows):
    """Summarise ``(stops, hitchhikers, no_ride)`` database rows.

    A no-ride record measures how long somebody waited before giving up, not how long
    it took to get a ride, so it is excluded. Malformed and unsupported durations are
    counted as missing rather than guessed; this is the same strict ``PT<n>M`` shape
    the map's own ride-facts code accepts.
    """
    values = defaultdict(list)
    coverage = {
        "rows_read": 0,
        "rides_used": 0,
        "no_ride_excluded": 0,
        "missing_wait_or_group": 0,
    }
    for stops, hitchhikers, no_ride in rows:
        coverage["rows_read"] += 1
        if no_ride:
            coverage["no_ride_excluded"] += 1
            continue
        wait = _wait_minutes(stops)
        composition = _composition(hitchhikers)
        if wait is None or composition is None:
            coverage["missing_wait_or_group"] += 1
            continue
        size = sum(composition)
        values[(size, composition)].append(wait)
        coverage["rides_used"] += 1

    groups = []
    for size in range(1, 5):
        combinations = []
        all_waits = []
        # Till asked for *all possible* gender combinations, not only cells that
        # happened to occur. Enumerate every multiset of the four values the form can
        # record, then add observed missing-gender compositions separately. Zero-sample
        # rows render with no median, which is more honest than silently omitting them.
        possible = set()
        for members in combinations_with_replacement(range(len(KNOWN_GENDERS)), size):
            counts = [0] * len(GENDER_ORDER)
            for index in members:
                counts[index] += 1
            possible.add(tuple(counts))
        possible.update(composition for row_size, composition in values if row_size == size and composition[-1])

        for composition in possible:
            waits = values.get((size, composition), [])
            all_waits.extend(waits)
            combinations.append(
                {
                    "gender_counts": [
                        {"gender": gender, "count": count} for gender, count in zip(GENDER_ORDER, composition) if count
                    ],
                    "median_minutes": _median(waits) if waits else None,
                    "rides": len(waits),
                    "has_unknown": composition[-1] > 0,
                }
            )
        # Known-gender combinations first, then larger samples. Every observed
        # combination remains present, including one-ride cells, because sample size is
        # printed beside the median rather than silently suppressing inconvenient data.
        combinations.sort(key=lambda row: (row["has_unknown"], row["rides"] == 0, -row["rides"], str(row["gender_counts"])))
        groups.append(
            {
                "size": size,
                "median_minutes": _median(all_waits) if all_waits else None,
                "rides": len(all_waits),
                "combinations": combinations,
            }
        )
    return {"coverage": coverage, "groups": groups}
