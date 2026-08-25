import json

from hitch.scripts.nostr_time import normalize_rfc9557_for_storage


def parse_post_to_ride_fields(post):
    """Turn one raw Nostr event dict into the column values for a RideEvent row.

    Returns a dict of RideEvent kwargs, or None when the event has empty / invalid
    content and should be skipped.

    Shared by fetch_nostr.py (full delete-and-recreate) and fetch_nostr_incremental.py
    (incremental upsert) so both ingestion paths extract exactly the same columns — the
    two must never drift, or an incrementally-imported ride would differ from the same
    ride after a full rebuild.
    """
    # Parse the 'content' field from JSON string to dict
    raw_content = post.get("content", "")
    if not isinstance(raw_content, str) or not raw_content.strip():
        return None
    try:
        content_json = json.loads(raw_content)
    except json.JSONDecodeError:
        return None

    # Extract 'expiration', 'd', and 'published_at' from tags
    tags_dict = {tag[0]: tag[1] for tag in post.get("tags", []) if len(tag) == 2}
    expiration = tags_dict.get("expiration")
    d = tags_dict.get("d")
    published_at = tags_dict.get("published_at")

    # `no_ride` is an object in the standard, but we only store whether it was present at all.
    # `would_ride_again` lives on the driver occupant; lift it out so it can be queried directly.
    driver = next(
        (o for o in (content_json.get("occupants") or []) if isinstance(o, dict) and o.get("was_driver")),
        None,
    )

    return dict(
        id=post.get("id"),
        kind=post.get("kind"),
        pubkey=post.get("pubkey"),
        sig=post.get("sig"),
        content=content_json,
        created_at=post.get("created_at"),
        version=content_json.get("version"),
        stops=content_json.get("stops"),
        signals=content_json.get("signals"),
        occupants=content_json.get("occupants"),
        hitchhikers=content_json.get("hitchhikers"),
        declined_rides=content_json.get("declined_rides"),
        no_ride=content_json.get("no_ride") is not None,
        would_ride_again=driver.get("would_ride_again") if driver else None,
        ride=content_json.get("ride"),
        mode_of_transportation=content_json.get("mode_of_transportation"),
        comment=content_json.get("comment"),
        rating=content_json.get("rating"),
        # Keep SQLite's text column uniform. RFC 9557 permits offsets (including Z)
        # and optional zone annotations; convert those instants to UTC, then store
        # the same timezone-free representation used by our existing records.
        submission_time=normalize_rfc9557_for_storage(content_json.get("submission_time")),
        license=content_json.get("license"),
        source=content_json.get("source"),
        expiration=expiration,
        d=d,
        published_at=published_at,
        tags=post.get("tags"),
    )
