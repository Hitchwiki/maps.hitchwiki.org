"""Weekly ride-collection aggregates for the public statistics page."""

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone


def _parse_timestamp(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _source(column_source, content):
    try:
        parsed = json.loads(content) if isinstance(content, str) else content
    except (TypeError, ValueError):
        parsed = None
    embedded = parsed.get("source") if isinstance(parsed, dict) else None
    return embedded or column_source or "Unknown"


def summarise_collection(rows, generated_at=None):
    """Return gap-free Monday buckets for all rides and every recorded source."""
    counts = defaultdict(Counter)
    invalid_timestamps = 0

    for submission_time, column_source, content in rows:
        stamp = _parse_timestamp(submission_time)
        if stamp is None:
            invalid_timestamps += 1
            continue
        monday = (stamp.date() - timedelta(days=stamp.weekday())).isoformat()
        counts[_source(column_source, content)][monday] += 1

    weeks_with_rides = [week for source_counts in counts.values() for week in source_counts]
    series = {}
    if weeks_with_rides:
        cursor = datetime.fromisoformat(min(weeks_with_rides)).date()
        last = datetime.fromisoformat(max(weeks_with_rides)).date()
        weeks = []
        while cursor <= last:
            weeks.append(cursor.isoformat())
            cursor += timedelta(days=7)

        all_counts = Counter()
        for source_counts in counts.values():
            all_counts.update(source_counts)
        series["All sources"] = [[week, all_counts[week]] for week in weeks]
        for source in sorted(counts, key=str.casefold):
            series[source] = [[week, counts[source][week]] for week in weeks]

    return {
        "generated_at": generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "series": series,
        "coverage": {
            "rides_used": sum(sum(source_counts.values()) for source_counts in counts.values()),
            "invalid_timestamps": invalid_timestamps,
        },
    }
