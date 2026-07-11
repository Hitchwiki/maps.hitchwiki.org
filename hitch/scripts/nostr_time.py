"""Timestamp normalization for Nostr ride ingestion."""

from datetime import datetime, timezone


def normalize_rfc9557_for_storage(value):
    """Return an RFC 9557 timestamp as a timezone-free UTC ISO string.

    SQLite stores ride timestamps as text.  Normalizing aware timestamps to UTC before
    dropping their timezone keeps that column uniform without changing the represented
    instant.  Existing timestamps without an offset are left as-is for compatibility.

    Python's ``datetime`` does not understand RFC 9557's optional bracketed annotations,
    but the numeric offset before the annotation is sufficient for this normalization.
    Invalid/non-string input is retained so ingestion remains lossless and downstream
    validation can handle it.
    """
    if not isinstance(value, str) or not value:
        return value

    timestamp = value.split("[", 1)[0]
    # Python <3.11 does not accept RFC 3339/9557's UTC designator directly.
    if timestamp.endswith(("Z", "z")):
        timestamp = f"{timestamp[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return value

    if parsed.tzinfo is None:
        return value

    return parsed.astimezone(timezone.utc).replace(tzinfo=None).isoformat()
