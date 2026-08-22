"""Intermediate ride stops ("onsen", "grandparents' house") -- the ride form's
"Stops along the way" input, label-only, no coordinate picker.

publish_ride.create_record_from_custom_object is the write side (custom_object dict ->
Stop objects); hitch.blueprints.utils.ride_facts.stop_facts is the read side, covered
in tests/test_ride_facts.py. This file pins the write side and the round trip between
them.
"""

import pytest

from hitch.blueprints import publish_ride
from hitch.blueprints.publish_ride import create_record_from_custom_object
from hitch.blueprints.utils.ride_facts import stop_facts


def _base_custom_object(**overrides):
    obj = {
        "pickup_lat": 51.08170,
        "pickup_lon": 13.73629,
        "destination_lat": 52.51739,
        "destination_lon": 13.39513,
        "datetime_ride": "",
        "arrival_datetime": "",
        "wait": None,
        "rate": 4,
        "comment": "",
        "signal": [],
        "co_hitchhiker": "",
    }
    obj.update(overrides)
    return obj


@pytest.fixture(autouse=True)
def _anonymous_user(monkeypatch):
    monkeypatch.setattr(publish_ride, "current_user", type("Anon", (), {"is_anonymous": True})())


def test_intermediate_stops_are_inserted_between_pickup_and_destination():
    record = create_record_from_custom_object(
        custom_object=_base_custom_object(ride_stops=["onsen", "grandparents' house"]),
        source="test",
        license="test",
    )
    assert len(record.stops) == 4  # pickup + 2 intermediate + destination
    assert record.stops[0].location.latitude == 51.08170  # pickup unchanged
    assert record.stops[-1].location.latitude == 52.51739  # destination unchanged

    intermediate = record.stops[1:-1]
    assert [s.label for s in intermediate] == ["onsen", "grandparents' house"]
    # Deliberately no coordinate -- see the module docstring.
    assert all(s.location is None for s in intermediate)


def test_intermediate_stops_keep_their_order():
    labels = ["gas station", "onsen", "viewpoint 39km away"]
    record = create_record_from_custom_object(custom_object=_base_custom_object(ride_stops=labels), source="test", license="test")
    assert [s.label for s in record.stops[1:-1]] == labels


def test_no_ride_stops_key_is_a_plain_two_stop_ride():
    """Missing key (not every caller sets it) must not raise, and must not add a stop."""
    record = create_record_from_custom_object(custom_object=_base_custom_object(), source="test", license="test")
    assert len(record.stops) == 2


def test_ride_stops_are_dropped_when_there_is_no_destination():
    # A stop "along the way" to nowhere recorded isn't a waypoint -- see the
    # comment in create_record_from_custom_object.
    record = create_record_from_custom_object(
        custom_object=_base_custom_object(destination_lat=None, destination_lon=None, ride_stops=["onsen"]),
        source="test",
        license="test",
    )
    assert len(record.stops) == 1  # pickup only, no intermediate, no destination


def test_write_then_read_round_trip_matches_the_form():
    """The exact path a real submission takes: build the record, dump it to the dict shape
    a Nostr event content actually carries, then read it back with stop_facts -- the same
    function /ride/<d_tag> and /pending_rides.json use."""
    record = create_record_from_custom_object(
        custom_object=_base_custom_object(ride_stops=["onsen"]), source="test", license="test"
    )
    stops_as_dicts = [s.model_dump() for s in record.stops]
    facts = stop_facts(stops_as_dicts)
    assert facts["pickup_lat"] == 51.08170
    assert facts["dest_lat"] == 52.51739
    assert len(facts["intermediate_stops"]) == 1
    assert facts["intermediate_stops"][0]["label"] == "onsen"
    assert facts["intermediate_stops"][0]["lat"] is None
