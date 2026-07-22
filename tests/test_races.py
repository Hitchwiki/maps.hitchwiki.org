"""Tests for the race parser and ranking (see RACES.md for the rules)."""

from datetime import datetime, timedelta, timezone

from hitch.scripts.races import build_races, current_races, parse_races_md, rank_race

BERLIN = (52.5200, 13.4050)
PRAGUE = (50.0755, 14.4378)
DRESDEN = (51.0504, 13.7373)

RACE = {
    "name": "Berlin → Prague",
    "start": {"name": "Berlin", "lat": BERLIN[0], "lon": BERLIN[1]},
    "finish": {"name": "Prague", "lat": PRAGUE[0], "lon": PRAGUE[1]},
    "from": datetime(2020, 1, 1, tzinfo=timezone.utc),
    "to": datetime(2030, 1, 1, tzinfo=timezone.utc),
    "max_gap_km": 10.0,
    "max_radius_km": 20.0,
}

T0 = datetime(2025, 6, 1, 8, 0, tzinfo=timezone.utc)


def ride(start_ll, dest_ll, depart_h, arrive_h):
    return {
        "lat": start_ll[0],
        "lon": start_ll[1],
        "dest_lat": dest_ll[0],
        "dest_lon": dest_ll[1],
        "start": T0 + timedelta(hours=depart_h),
        "end": T0 + timedelta(hours=arrive_h),
        "card": {},
    }


def test_parse_races_md_reads_the_real_file():
    races = parse_races_md("RACES.md")
    assert races, "RACES.md should define at least one race"
    first = races[0]
    assert first["start"]["name"] and first["finish"]["name"]
    assert first["from"] < first["to"]
    # The format example lives in a fenced code block and must not become a race.
    assert not any(r["start"]["name"] == "Berlin" and r["finish"]["name"] == "Amsterdam" for r in races)


def test_two_leg_chain_ranks_and_reports_its_duration():
    rides = {"anna": [ride(BERLIN, DRESDEN, 0, 2), ride(DRESDEN, PRAGUE, 3, 5)]}
    (entry,) = rank_race(RACE, rides)
    assert entry["hitchhiker_name"] == "anna"
    assert entry["duration_s"] == 5 * 3600  # first departure -> last arrival, waiting included
    assert len(entry["rides"]) == 2


def test_fastest_of_several_attempts_wins_and_podium_is_sorted():
    rides = {
        "anna": [ride(BERLIN, PRAGUE, 0, 6), ride(BERLIN, PRAGUE, 100, 104)],  # 2nd attempt faster
        "bob": [ride(BERLIN, PRAGUE, 0, 5)],
    }
    podium = rank_race(RACE, rides)
    assert [e["hitchhiker_name"] for e in podium] == ["anna", "bob"]
    assert podium[0]["duration_s"] == 4 * 3600


def test_only_the_top_three_are_returned():
    rides = {f"h{i}": [ride(BERLIN, PRAGUE, 0, i + 1)] for i in range(6)}
    assert len(rank_race(RACE, rides)) == 3


def test_a_gap_between_rides_breaks_the_chain():
    # Dropped off in Dresden but picked up 60 km away — not consecutive, so no journey.
    far = (51.5, 14.5)
    rides = {"anna": [ride(BERLIN, DRESDEN, 0, 2), ride(far, PRAGUE, 3, 5)]}
    assert rank_race(RACE, rides) == []


def test_rides_must_not_overlap_in_time():
    # The second leg departs before the first arrived, so they cannot be one journey.
    rides = {"anna": [ride(BERLIN, DRESDEN, 0, 4), ride(DRESDEN, PRAGUE, 2, 5)]}
    assert rank_race(RACE, rides) == []


def test_stopover_longer_than_the_leg_limit_breaks_the_chain():
    rides = {"anna": [ride(BERLIN, DRESDEN, 0, 2), ride(DRESDEN, PRAGUE, 24 * 3, 24 * 3 + 2)]}
    assert rank_race(RACE, rides) == []


def test_start_and_finish_must_be_near_the_city_centres():
    off_target = (48.2082, 16.3738)  # Vienna
    assert rank_race(RACE, {"anna": [ride(BERLIN, off_target, 0, 5)]}) == []
    assert rank_race(RACE, {"anna": [ride(off_target, PRAGUE, 0, 5)]}) == []


def test_rides_outside_the_timespan_do_not_count():
    race = dict(RACE, **{"from": datetime(2026, 1, 1, tzinfo=timezone.utc)})
    assert rank_race(race, {"anna": [ride(BERLIN, PRAGUE, 0, 5)]}) == []


NOW = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)


def _race(name, frm, to):
    return {"name": name, "from": frm, "to": to}


def test_only_running_and_soon_starting_races_are_listed():
    races = [
        _race("running", "2026-01-01", "2026-12-31"),
        _race("ends today", "2026-01-01", "2026-07-22"),
        _race("starts next week", "2026-07-29", "2026-08-02"),
        _race("ended yesterday", "2026-06-01", "2026-07-21"),
        _race("starts in three months", "2026-10-01", "2026-10-05"),
    ]
    shown = current_races(races, now=NOW)
    assert [r["name"] for r in shown] == ["ends today", "running", "starts next week"]
    assert shown[0]["status"] == "running"
    assert shown[-1]["status"] == "upcoming"
    assert shown[-1]["starts_in_days"] == 7


def test_running_races_sort_before_upcoming_ones():
    races = [_race("soon", "2026-08-01", "2026-08-05"), _race("now", "2026-07-01", "2026-08-01")]
    assert [r["status"] for r in current_races(races, now=NOW)] == ["running", "upcoming"]


def test_unparseable_dates_are_dropped_rather_than_raising():
    assert current_races([_race("broken", "not-a-date", "2026-12-31")], now=NOW) == []


def test_race_titles_fall_back_to_virtual_race(tmp_path):
    md = tmp_path / "RACES.md"
    md.write_text(
        "## Berlin → Prague\n"
        "- start: Berlin, 52.5200, 13.4050\n"
        "- finish: Prague, 50.0755, 14.4378\n"
        "- from: 2020-01-01\n- to: 2030-01-01\n\n"
        "## Berlin → Amsterdam\n"
        "- start: Berlin, 52.5200, 13.4050\n"
        "- finish: Amsterdam, 52.3731, 4.8922\n"
        "- from: 2020-01-01\n- to: 2030-01-01\n"
        "- name: Tramprennen\n",
        encoding="utf-8",
    )
    titles = [r["title"] for r in parse_races_md(str(md))]
    assert titles == ["Virtual race Berlin → Prague", "Tramprennen Berlin → Amsterdam"]


def test_build_races_shapes_the_json_the_page_reads():
    out = build_races("RACES.md", {"anna": [ride(BERLIN, PRAGUE, 0, 5)]})
    berlin_prague = [r for r in out if r["start"] == "Berlin" and r["finish"] == "Prague"]
    assert berlin_prague, "RACES.md should still define Berlin → Prague"
    assert berlin_prague[0]["entries"][0]["hitchhiker_name"] == "anna"
