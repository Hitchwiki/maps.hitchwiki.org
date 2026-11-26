"""#410: 'Other people in the car' must survive a save and come back on edit."""

import re

import pytest

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


class _Poster:
    records = []
    last_event = None

    def post(self, ride_record, tags=None, d_tag=None):
        _Poster.records.append(ride_record)
        return build_ride_d_tag("hitchmap", tags, d_tag)

    def close(self):
        pass


@pytest.mark.parametrize("value,expected", [("0", 1), ("1", 2), ("2", 3), ("3", 4)])
def test_ride_form_post_publishes_companions(client, monkeypatch, value, expected):
    _Poster.records = []
    monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _Poster)
    r = client.post(
        "/ride", data=dict(_FORM, driver_companions=value, client_d_tag=f"c410-{value}"), headers={"X-Requested-With": "inride"}
    )
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    occ = _Poster.records[-1].occupants
    assert occ is not None and len(occ) == expected


def _selected(body):
    m = re.search(r'<select id="driver_companions".*?</select>', body, re.S)
    sel = re.search(r'<option value="([^"]*)"\s*selected', m.group(0))
    return sel.group(1) if sel else None


@pytest.mark.parametrize("others,expected", [(0, "0"), (2, "2")])
def test_edit_prefills_companions(app, client, others, expected):
    from hitch.extensions import db as _db
    from hitch.models import RideEvent, User
    from tests.conftest import TEST_PUBKEY

    username, d_tag, uq = "comp410owner", f"hitchmap-comp410-{others}", "comp410-uniq"
    with app.app_context():
        _db.session.query(RideEvent).filter_by(d=d_tag).delete()
        _db.session.query(User).filter_by(username=username).delete()
        _db.session.add(User(username=username, email="c410@example.com", password="x", active=True, fs_uniquifier=uq))
        _db.session.add(
            RideEvent(
                id=f"comp410evt{others}",
                pubkey=TEST_PUBKEY,
                sig="s" * 128,
                kind=36820,
                created_at=1_800_000_000,
                d=d_tag,
                tags=[["d", d_tag], ["published_at", "1800000000"]],
                content={
                    "version": "1.0.0",
                    "source": "hitchmap.com",
                    "comment": "x",
                    "rating": 4,
                    "submission_time": "2026-07-01T10:00:00",
                    "hitchhikers": [{"nickname": username}],
                    "stops": [
                        {"location": {"latitude": 52.0, "longitude": 13.0}},
                        {"location": {"latitude": 52.1, "longitude": 13.1}},
                    ],
                    "occupants": [{"was_driver": True}] + [{"was_driver": False}] * others,
                },
            )
        )
        _db.session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = uq
        sess["_fresh"] = True
    try:
        body = client.get(f"/ride?edit={d_tag}").get_data(as_text=True)
        assert _selected(body) == expected
    finally:
        with client.session_transaction() as sess:
            sess.clear()
        with app.app_context():
            _db.session.query(RideEvent).filter_by(d=d_tag).delete()
            _db.session.query(User).filter_by(username=username).delete()
            _db.session.commit()
