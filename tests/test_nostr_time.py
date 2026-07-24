from hitch.scripts.nostr_time import normalize_rfc9557_for_storage


def test_normalizes_z_timestamp_to_timezone_free_utc():
    assert normalize_rfc9557_for_storage("2026-07-11T16:23:28Z") == "2026-07-11T16:23:28"


def test_normalizes_offset_and_rfc9557_zone_annotation_to_utc():
    assert normalize_rfc9557_for_storage("2025-05-19T17:39:57-08:00[America/Los_Angeles]") == "2025-05-20T01:39:57"


def test_leaves_timezone_free_and_invalid_values_unchanged():
    assert normalize_rfc9557_for_storage("2026-07-11T16:23:28") == "2026-07-11T16:23:28"
    assert normalize_rfc9557_for_storage("not-a-timestamp") == "not-a-timestamp"
    assert normalize_rfc9557_for_storage(None) is None
