"""The ride form / in-ride sheet post `signal` as a list of short codes; the backend
maps them onto the hitchhiking-data-standard `methods` enum. These pin that mapping,
including the `unsolicited` value (driver stopped with no signal made) added so a ride
where the hitchhiker did nothing is still recordable.
"""

from hitch.blueprints import publish_ride
from hitch.blueprints.publish_ride import create_record_from_custom_object


def _record(signal, monkeypatch):
    monkeypatch.setattr(publish_ride, "current_user", type("Anon", (), {"is_anonymous": True})())
    return create_record_from_custom_object(
        custom_object={
            "pickup_lat": 51.0,
            "pickup_lon": 13.0,
            "destination_lat": None,
            "destination_lon": None,
            "datetime_ride": "",
            "wait": None,
            "rate": 4,
            "comment": "",
            "signal": signal,
        },
        source="test",
        license="test",
    )


def test_known_codes_map_to_standard_methods(monkeypatch):
    record = _record(["thumb", "sign", "ask"], monkeypatch)
    assert record.signals[0].methods == ["thumb", "sign", "asking"]


def test_unsolicited_is_carried_through(monkeypatch):
    record = _record(["unsolicited"], monkeypatch)
    assert record.signals[0].methods == ["unsolicited"]


def test_empty_signal_produces_no_signals(monkeypatch):
    assert _record([], monkeypatch).signals is None
