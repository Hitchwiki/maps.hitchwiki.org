"""Other people in the car besides the driver (maps issue #350): each one lands as a
bare Occupant(was_driver=False) next to the driver, capped at 3 ("3 or more")."""

import pytest

from hitch.blueprints import publish_ride
from hitch.blueprints.publish_ride import create_record_from_custom_object


def _obj(**overrides):
    obj = {
        "pickup_lat": 51.0817,
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


def _record(**kw):
    return create_record_from_custom_object(custom_object=_obj(**kw), source="test", license="test")


def test_companions_become_extra_occupants():
    record = _record(driver_gender="female", driver_companions="2")
    assert len(record.occupants) == 3
    assert [o.was_driver for o in record.occupants] == [True, False, False]


def test_companions_alone_still_emit_occupants():
    assert len(_record(driver_companions="1").occupants) == 2


def test_unanswered_or_zero_adds_nothing():
    assert _record().occupants is None
    assert len(_record(driver_gender="male", driver_companions="0").occupants) == 1
    assert len(_record(driver_gender="male", driver_companions="").occupants) == 1


def test_capped_at_three():
    assert len(_record(driver_companions="9").occupants) == 4


def test_retrospective_ride_form_has_companions_select():
    """/ride form (not only the in-ride sheet) lets people answer, and keeps it across map round-trips."""
    from pathlib import Path

    tpl = (Path(__file__).parents[1] / "hitch" / "templates" / "ride_form.html").read_text()
    assert 'name="driver_companions"' in tpl
    assert "driver_companions: document.getElementById('driver_companions')" in tpl
    assert "data.driver_companions !== undefined" in tpl


def test_ride_detail_shows_companions():
    from pathlib import Path

    root = Path(__file__).parents[1] / "hitch"
    assert "driver[\"companions\"]" in (root / "blueprints" / "main.py").read_text()
    assert "ride.driver.companions" in (root / "templates" / "ride_detail.html").read_text()
