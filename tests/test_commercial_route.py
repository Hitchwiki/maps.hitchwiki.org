import hitch.blueprints.main as main


class _CapturePoster:
    """Captures the record so the test can assert commercial round-trips through /ride."""

    captured = {}

    def post(self, ride_record, tags=None, d_tag=None):
        _CapturePoster.captured["record"] = ride_record
        return "dtag123"

    def close(self):
        pass


def _post(client, **extra):
    data = {
        "rate": "4",
        "wait": "10",
        "signal": "thumb",
        "comment": "",
        "pickup_lat": "48.2",
        "pickup_lon": "16.37",
        "destination_lat": "48.5",
        "destination_lon": "16.9",
        "datetime_ride": "2026-07-02T14:00",
        "arrival_datetime": "2026-07-02T14:41",
        "vehicle_kind": "van",
    }
    data.update(extra)
    return client.post("/ride", data=data, headers={"X-Requested-With": "inride"})


def test_commercial_true_posts_through(client, monkeypatch):
    monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _CapturePoster)
    resp = _post(client, vehicle_commercial="true")
    assert resp.status_code == 200
    assert _CapturePoster.captured["record"].mode_of_transportation.commercial is True


def test_commercial_false_posts_through(client, monkeypatch):
    monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _CapturePoster)
    resp = _post(client, vehicle_commercial="false")
    assert resp.status_code == 200
    assert _CapturePoster.captured["record"].mode_of_transportation.commercial is False


def test_commercial_absent_is_none(client, monkeypatch):
    monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _CapturePoster)
    resp = _post(client)
    assert resp.status_code == 200
    assert _CapturePoster.captured["record"].mode_of_transportation.commercial is None
