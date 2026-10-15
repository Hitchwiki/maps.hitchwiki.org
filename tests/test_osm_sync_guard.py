from datetime import datetime, timezone

from hitch.osm_sync_guard import data_age_problem, shrink_problem

NOW = datetime(2026, 10, 15, 3, 0, tzinfo=timezone.utc)


def test_stale_mirror_rejected():
    assert data_age_problem({"osm3s": {"timestamp_osm_base": "2026-06-01T00:00:00Z"}}, NOW)


def test_fresh_and_missing_timestamp_accepted():
    assert data_age_problem({"osm3s": {"timestamp_osm_base": "2026-10-15T02:30:00Z"}}, NOW) is None
    assert data_age_problem({}, NOW) is None


def test_forty_percent_drop_rejected_small_drop_ok():
    assert shrink_problem(933, 1471)
    assert shrink_problem(1400, 1471) is None
    assert shrink_problem(5, 0) is None
