import hitch.blueprints.main as main


class _FakePoster:
    """Stub for HitchhikingDataStandardToNostrPoster — no network calls."""

    last_event = None

    def post(self, ride_record, tags=None, d_tag=None):
        return "dtag123"

    def close(self):
        pass


# In-ride submissions must get JSON back (not a redirect) so the map UI can stay put.
def test_inride_submit_returns_json_ok(client, monkeypatch):
    monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _FakePoster)
    resp = client.post(
        "/ride",
        data={
            "rate": "4",
            "wait": "12",
            "signal": "thumb",
            "comment": "",
            "pickup_lat": "48.2",
            "pickup_lon": "16.37",
            "destination_lat": "48.5",
            "destination_lon": "16.9",
            "datetime_ride": "2026-07-02T14:00",
            "arrival_datetime": "2026-07-02T14:41",
        },
        headers={"X-Requested-With": "inride"},
    )
    assert resp.status_code == 200
    assert resp.is_json
    assert resp.get_json()["ok"] is True
    assert resp.get_json()["d_tag"] == "dtag123"


# Validation failures must also return JSON (not a redirect or unhandled exception) for inride.
def test_inride_submit_returns_json_error_on_invalid_payload(client, monkeypatch):
    monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _FakePoster)
    # rate=99 is out of range (1-5) and will trigger the AssertionError in the handler.
    resp = client.post(
        "/ride",
        data={
            "rate": "99",
            "wait": "12",
            "signal": "thumb",
            "comment": "",
            "pickup_lat": "48.2",
            "pickup_lon": "16.37",
            "destination_lat": "48.5",
            "destination_lon": "16.9",
            "datetime_ride": "2026-07-02T14:00",
            "arrival_datetime": "2026-07-02T14:41",
        },
        headers={"X-Requested-With": "inride"},
    )
    assert resp.status_code == 400
    assert resp.is_json
    data = resp.get_json()
    assert data["ok"] is False
    assert "error" in data
