"""A stale optional enum value (old cached form, localStorage draft) must be dropped
with a log line, not reject the whole ride. Required fields still return 400."""

import hitch.blueprints.main as main
from hitch.blueprints.utils.post_hitchhiking_ride_to_nostr import build_ride_d_tag

_FORM = {
    "rate": "4",
    "wait": "10",
    "signal": "",
    "comment": "",
    "vehicle_kind": "",
    "pickup_lat": "52.0",
    "pickup_lon": "13.0",
    "destination_lat": "52.1",
    "destination_lon": "13.1",
    "datetime_ride": "2026-07-08T10:00",
    "arrival_datetime": "2026-07-08T10:20",
}
_HEADERS = {"X-Requested-With": "inride"}


class _Poster:
    last_event = None

    def post(self, ride_record, tags=None, d_tag=None):
        return build_ride_d_tag("hitchmap", tags, d_tag)

    def close(self):
        pass


def test_invalid_optional_values_are_dropped_not_rejected(client, monkeypatch):
    monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _Poster)
    form = dict(_FORM, vehicle_kind="spaceship", driver_gender="bogus", client_d_tag="drift-1")
    r = client.post("/ride", data=form, headers=_HEADERS)
    assert r.status_code == 200
    assert r.get_json()["ok"]


def test_invalid_required_field_still_returns_400(client, monkeypatch):
    monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _Poster)
    form = dict(_FORM, pickup_lat="not-a-number", client_d_tag="drift-2")
    r = client.post("/ride", data=form, headers=_HEADERS)
    assert r.status_code == 400
