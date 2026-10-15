"""Pure checks that decide whether an Overpass answer may replace the osm_hitchhiking_spot table."""

from datetime import datetime, timedelta, timezone

MAX_DATA_AGE = timedelta(hours=48)
MIN_KEEP_RATIO = 0.9


def data_age_problem(candidate, now=None):
    """Return a reason string when the answer's data is older than MAX_DATA_AGE, else None.

    A mirror that lags behind (2026-10-15: one served a database frozen on 2026-06-01) answers 200 with no remark, so
    only `osm3s.timestamp_osm_base` reveals it. A missing timestamp is accepted: refusing it would stop the sync on a
    mirror that merely omits the field.
    """
    stamp = (candidate.get("osm3s") or {}).get("timestamp_osm_base")
    if not stamp:
        return None
    try:
        base = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    if now - base > MAX_DATA_AGE:
        return f"data is from {stamp}, older than {MAX_DATA_AGE}"
    return None


def shrink_problem(new_count, prior_count):
    """Return a reason string when the new set is under MIN_KEEP_RATIO of the stored one, else None."""
    if prior_count and new_count < prior_count * MIN_KEEP_RATIO:
        return f"{new_count} nodes vs {prior_count} stored (< {MIN_KEEP_RATIO:.0%})"
    return None
