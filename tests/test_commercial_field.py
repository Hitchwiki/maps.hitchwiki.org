from hitch.blueprints.publish_ride import create_record_from_custom_object


def _base_object(**extra):
    obj = {
        "rate": 4,
        "wait": 10,
        "signal": [],
        "comment": None,
        "pickup_lat": 48.2,
        "pickup_lon": 16.37,
        "destination_lat": 48.5,
        "destination_lon": 16.9,
        "datetime_ride": "2026-07-02T14:00",
        "arrival_datetime": "2026-07-02T14:41",
        "vehicle_kind": "van",
    }
    obj.update(extra)
    return obj


def test_commercial_true_serialized_into_transport(app):
    with app.test_request_context():
        rec = create_record_from_custom_object(_base_object(vehicle_commercial=True), "hitchmap", "CC0")
        assert rec.mode_of_transportation.commercial is True


def test_commercial_false_serialized_into_transport(app):
    with app.test_request_context():
        rec = create_record_from_custom_object(_base_object(vehicle_commercial=False), "hitchmap", "CC0")
        assert rec.mode_of_transportation.commercial is False


def test_commercial_absent_is_none(app):
    with app.test_request_context():
        rec = create_record_from_custom_object(_base_object(), "hitchmap", "CC0")
        assert rec.mode_of_transportation.commercial is None
