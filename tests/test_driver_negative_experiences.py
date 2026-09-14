"""B591: a gentle, structured way to record why a hitchhiker would not take a ride
with this driver again -- the standard's Occupant.negative_experiences, wired onto
the /ride form's "Would you accept this ride again?" No answer.

publish_ride.create_record_from_custom_object is the write side (custom_object dict
-> Occupant); main.py's _view_ride_data-style extraction (the `driver` dict built for
ride_detail.html) is the read side, exercised indirectly via ride_view_from_content
where feasible. This file pins the write side.
"""

import pytest

from hitch.blueprints import publish_ride
from hitch.blueprints.publish_ride import create_record_from_custom_object


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


def test_negative_experiences_land_on_the_driver_occupant():
    record = create_record_from_custom_object(
        custom_object=_base_custom_object(
            driver_would_ride_again=False,
            driver_negative_experiences=["unsafe_driving", "felt_unsafe"],
        ),
        source="test",
        license="test",
    )
    driver = next(o for o in record.occupants if o.was_driver)
    assert driver.would_ride_again is False
    assert driver.negative_experiences == ["unsafe_driving", "felt_unsafe"]


def test_no_negative_experiences_key_is_a_plain_occupant():
    """Missing key (not every caller sets it) must not raise, and must not fabricate a value."""
    record = create_record_from_custom_object(
        custom_object=_base_custom_object(driver_would_ride_again=True),
        source="test",
        license="test",
    )
    driver = next(o for o in record.occupants if o.was_driver)
    assert driver.negative_experiences is None


def test_empty_negative_experiences_list_is_none_not_empty_list():
    # Occupant(negative_experiences=[]) would publish a Nostr event that claims an
    # (empty) answer was given; None means "not asked / not answered".
    record = create_record_from_custom_object(
        custom_object=_base_custom_object(driver_would_ride_again=True, driver_negative_experiences=[]),
        source="test",
        license="test",
    )
    driver = next(o for o in record.occupants if o.was_driver)
    assert driver.negative_experiences is None
