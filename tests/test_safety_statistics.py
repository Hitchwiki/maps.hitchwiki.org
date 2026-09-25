"""Row building behind /hitchhiking-safety (hitch/blueprints/utils/safety_statistics.py)."""

import json

from hitch.blueprints.utils.safety_statistics import pickup_coords, summarise_rows

DEFAULT_STOP = {"location": {"latitude": 50.0, "longitude": 8.0}, "waiting_duration": "PT10M"}


def row(
    ride_id="e1",
    d_tag="d1",
    hitchhikers=None,
    occupants=None,
    stops=None,
    vehicle=None,
    signals=None,
    rating=None,
    submission_time="2026-07-09T18:01:16",
    no_ride=None,
    would_ride_again=True,
):
    return (
        ride_id,
        d_tag,
        json.dumps(hitchhikers if hitchhikers is not None else [{"nickname": "Ada", "gender": "female", "year_of_birth": 1999}]),
        json.dumps(occupants if occupants is not None else [{"was_driver": True, "would_ride_again": would_ride_again}]),
        json.dumps(stops if stops is not None else [DEFAULT_STOP]),
        json.dumps(vehicle) if vehicle else None,
        json.dumps(signals) if signals else None,
        rating,
        submission_time,
        no_ride,
        would_ride_again,
    )


def test_only_answered_rides_are_rows():
    result = summarise_rows([row(), row(ride_id="e2", would_ride_again=None), row(ride_id="e3", would_ride_again=False)])
    assert result["coverage"]["rows_read"] == 3
    assert result["coverage"]["no_answer"] == 1
    assert result["coverage"]["rides_used"] == 2
    assert result["coverage"]["yes"] == 1
    assert [ride["w"] for ride in result["rides"]] == [1, 0]


def test_give_up_records_never_count():
    """A no_ride entry has no driver to answer about, so it cannot vote in the rate."""
    result = summarise_rows([row(no_ride=1)])
    assert result["rides"] == []
    assert result["coverage"]["no_ride_excluded"] == 1


def test_age_is_taken_at_the_time_of_the_ride():
    """Departure time wins over submission time: a ride logged months later must not
    age its hitchhiker by a year."""
    stops = [{"location": {"latitude": 50.0, "longitude": 8.0}, "departure_time": "2025-08-01T14:00:00"}]
    result = summarise_rows([row(stops=stops, submission_time="2026-01-02T09:00:00")])
    assert result["rides"][0]["p"] == [["female", 2025 - 1999, None]]
    assert result["rides"][0]["y"] == 2025


def test_hour_comes_only_from_departure_time():
    """The submission stamp is when someone typed the ride in — often the evening of a
    morning ride — so it must never feed the time-of-day breakdown."""
    without = summarise_rows([row(submission_time="2026-07-09T23:32:15")])["rides"][0]
    assert "h" not in without
    stops = [{"location": {"latitude": 50.0, "longitude": 8.0}, "departure_time": "2026-07-09T07:15:00"}]
    assert summarise_rows([row(stops=stops)])["rides"][0]["h"] == 7


def test_implausible_birth_years_are_dropped():
    people = [{"nickname": "Ada", "gender": "female", "year_of_birth": 19}]
    assert summarise_rows([row(hitchhikers=people)])["rides"][0]["p"] == [["female", None, None]]


def test_unknown_gender_is_not_a_gender():
    people = [{"nickname": "Ada", "gender": "alien"}]
    assert summarise_rows([row(hitchhikers=people)])["rides"][0]["p"] == [[None, None, None]]


def test_driver_facts_and_negative_experiences():
    driver = {
        "was_driver": True,
        "would_ride_again": False,
        "gender": "male",
        "year_of_birth": 1970,
        "negative_experiences": ["felt_unsafe"],
    }
    occupants = [driver, {"gender": "female"}]
    result = summarise_rows([row(occupants=occupants, would_ride_again=False)])
    ride = result["rides"][0]
    assert ride["dg"] == "male"
    assert ride["da"] == 2026 - 1970
    assert ride["n"] == ["felt_unsafe"]
    assert result["negative_experiences"] == {"felt_unsafe": 1}


def test_distance_uses_both_ends_or_nothing():
    stops = [
        {"location": {"latitude": 50.0, "longitude": 8.0}, "waiting_duration": "PT10M"},
        {"location": {"latitude": 50.5, "longitude": 8.0}},
    ]
    assert summarise_rows([row(stops=stops)])["rides"][0]["km"] == 55.6
    assert "km" not in summarise_rows([row()])["rides"][0]


def test_named_hitchhikers_exclude_the_anonymous_sentinel():
    result = summarise_rows(
        [
            row(hitchhikers=[{"nickname": "Anonymous"}]),
            row(ride_id="e2", hitchhikers=[{"nickname": "Ada"}]),
            row(ride_id="e3", hitchhikers=[{"nickname": "Ada"}]),
        ]
    )
    assert result["coverage"]["named_hitchhikers"] == 1


def test_malformed_waiting_duration_reads_as_missing():
    """Same strict PT<n>M rule as ride_facts: an invented wait would pollute the bands."""
    stops = [{"location": {"latitude": 50.0, "longitude": 8.0}, "waiting_duration": "PT2H"}]
    assert "wt" not in summarise_rows([row(stops=stops)])["rides"][0]


def test_pickup_coords_reads_the_first_stop():
    assert pickup_coords([{"location": {"latitude": 1.5, "longitude": 2.5}}]) == (1.5, 2.5)
    assert pickup_coords(None) == (None, None)


def test_countries_are_attached_by_ride_id():
    result = summarise_rows([row(ride_id="e1")], countries={"e1": "DE"})
    assert result["rides"][0]["cc"] == "DE"
