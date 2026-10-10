"""Maps issue #351: a stop typed as pasted coordinates publishes with a real location."""

import pytest

from hitch.blueprints import publish_ride
from hitch.blueprints.publish_ride import create_record_from_custom_object, parse_coordinate_stop


@pytest.fixture(autouse=True)
def _anonymous_user(monkeypatch):
    monkeypatch.setattr(publish_ride, "current_user", type("Anon", (), {"is_anonymous": True})())


@pytest.mark.parametrize(
    "label,expected",
    [
        ("48.2082, 16.3738", (48.2082, 16.3738, None)),
        ("48.2082 16.3738 Vienna rest area", (48.2082, 16.3738, "Vienna rest area")),
        ("-33.86;151.2 - harbour", (-33.86, 151.2, "harbour")),
        ("onsen", None),
        ("91.0, 10.0", None),
        ("12 bus stops", None),
    ],
)
def test_parse(label, expected):
    assert parse_coordinate_stop(label) == expected


def test_coordinate_stop_gets_a_location_between_pickup_and_destination():
    obj = {
        "pickup_lat": 48.0,
        "pickup_lon": 16.0,
        "destination_lat": 49.0,
        "destination_lon": 17.0,
        "datetime_ride": "",
        "arrival_datetime": "",
        "wait": None,
        "rate": 4,
        "comment": "",
        "signal": [],
        "co_hitchhiker": "",
        "ride_stops": ["48.5, 16.5 petrol station", "onsen"],
    }
    record = create_record_from_custom_object(custom_object=obj, source="t", license="t")
    mid = record.stops[1:-1]
    assert mid[0].location.latitude == 48.5 and mid[0].location.longitude == 16.5
    assert mid[0].label == "petrol station"
    assert mid[1].location is None and mid[1].label == "onsen"
