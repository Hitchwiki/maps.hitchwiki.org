"""Intermediate ride stops ("onsen", "grandparents' house") -- the ride form's
"Stops along the way" input, label-only, no coordinate picker.

publish_ride.create_record_from_custom_object is the write side (custom_object dict ->
Stop objects); hitch.blueprints.utils.ride_facts.stop_facts is the read side, covered
in tests/test_ride_facts.py. This file pins the write side and the round trip between
them.
"""

import pytest

from hitch.blueprints import publish_ride
from hitch.blueprints.publish_ride import create_record_from_custom_object, foreign_coordinate_intermediate_stops
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


# ── foreign_coordinate_intermediate_stops (edit-safety guard) ──────────────────────
class TestForeignCoordinateIntermediateStops:
    def test_a_coordinate_bearing_stop_is_preserved(self):
        raw = [
            {"location": {"latitude": 51.0, "longitude": 13.0}},  # pickup
            {"location": {"latitude": 51.5, "longitude": 13.2}, "label": "roadside shrine"},
            {"location": {"latitude": 52.0, "longitude": 13.5}},  # destination
        ]
        preserved = foreign_coordinate_intermediate_stops(raw)
        assert len(preserved) == 1
        assert preserved[0].location.latitude == 51.5
        assert preserved[0].location.longitude == 13.2
        assert preserved[0].label == "roadside shrine"

    def test_a_label_only_stop_is_not_preserved(self):
        # This form's own shape -- it round-trips through the ride_stops chip input,
        # not this guard.
        raw = [
            {"location": {"latitude": 51.0, "longitude": 13.0}},
            {"location": None, "label": "onsen"},
            {"location": {"latitude": 52.0, "longitude": 13.5}},
        ]
        assert foreign_coordinate_intermediate_stops(raw) == []

    def test_pickup_and_destination_are_never_included(self):
        raw = [
            {"location": {"latitude": 51.0, "longitude": 13.0}},
            {"location": {"latitude": 52.0, "longitude": 13.5}},
        ]
        assert foreign_coordinate_intermediate_stops(raw) == []

    def test_empty_and_malformed_input_yields_nothing(self):
        for raw in ([], None, "not a list", [{}], [{"location": {}}]):
            assert foreign_coordinate_intermediate_stops(raw) == []

    def test_a_malformed_middle_entry_with_no_usable_coordinate_is_skipped(self):
        raw = [
            {"location": {"latitude": 51.0, "longitude": 13.0}},
            {"location": {}},  # neither a coordinate nor a label -- nothing to preserve
            "not even a dict",
            {"location": {"latitude": 52.0, "longitude": 13.5}},
        ]
        assert foreign_coordinate_intermediate_stops(raw) == []
