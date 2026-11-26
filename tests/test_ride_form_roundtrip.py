"""Every field the /ride form posts must come back when the same ride is opened for editing.

#410 was one instance of "chose it, saved it, edit shows it blank" (Driver alone). This test
posts every field at once, stores the published record the way _store_published_ride would,
opens /ride?edit=<d> and compares the ride_data the template receives against what was sent,
so any other field with the same save or prefill loss fails here by name.
"""

import json

import pytest

import hitch.blueprints.main as main
from hitch.blueprints.utils.driver_info_choices import (
    ALLOWED_NEGATIVE_EXPERIENCES,
    ALLOWED_REASONS_TO_HITCHHIKE,
    ALLOWED_REASONS_TO_PICK_UP,
    ALLOWED_RIDE_REASONS,
)
from hitch.blueprints.utils.post_hitchhiking_ride_to_nostr import build_ride_d_tag
from hitch.scripts.nostr_ride_parsing import parse_post_to_ride_fields

USERNAME, UQ = "roundtripowner", "roundtrip-uniq"

# Expected value in ride_data for each posted field (None = same string as posted).
FORM = {
    "rate": ("4", 4),  # read back as ride_data["rating"]
    "wait": ("25", 25),
    "comment": ("Roundtrip comment", None),
    "pickup_lat": ("52.0", 52.0),
    "pickup_lon": ("13.0", 13.0),
    "destination_lat": ("52.1", 52.1),
    "destination_lon": ("13.1", 13.1),
    "datetime_ride": ("2026-07-08T10:00", None),
    "arrival_datetime": ("2026-07-08T10:20", None),
    "signal": ("thumb,sign", ["sign", "thumb"]),
    "sign_content": ("BERLIN", None),
    "ride_stops": ('["Halle"]', ["Halle"]),
    "vehicle_kind": ("car", None),
    "vehicle_make": ("VW", None),
    "vehicle_model": ("Golf", None),
    "vehicle_license_plate_country": ("DE", None),
    "vehicle_license_plate_identifier": ("B-XY-123", None),
    "driver_gender": ("female", None),
    "driver_age": ("40", None),
    "driver_origin_country": ("DE", None),
    "driver_languages": ("deu", ["deu"]),
    "driver_would_ride_again": ("no", None),
    "driver_reason_to_pick_up": (ALLOWED_REASONS_TO_PICK_UP[0], [ALLOWED_REASONS_TO_PICK_UP[0]]),
    "driver_negative_experiences": (ALLOWED_NEGATIVE_EXPERIENCES[0], [ALLOWED_NEGATIVE_EXPERIENCES[0]]),
    "driver_companions": ("2", None),
    "ride_reasons": (ALLOWED_RIDE_REASONS[0], [ALLOWED_RIDE_REASONS[0]]),
    "reasons_to_hitchhike": (ALLOWED_REASONS_TO_HITCHHIKE[0], [ALLOWED_REASONS_TO_HITCHHIKE[0]]),
}


class _Poster:
    records = []
    last_event = None

    def post(self, ride_record, tags=None, d_tag=None):
        _Poster.records.append(ride_record)
        return build_ride_d_tag("hitchmap", tags, d_tag)

    def close(self):
        pass


def _norm(v):
    if isinstance(v, list):
        return sorted(str(x) for x in v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return v


@pytest.fixture
def owner(app, client):
    from hitch.extensions import db as _db
    from hitch.models import RideEvent, User

    with app.app_context():
        _db.session.query(User).filter_by(username=USERNAME).delete()
        _db.session.add(User(username=USERNAME, email="rt@example.com", password="x", active=True, fs_uniquifier=UQ))
        _db.session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = UQ
        sess["_fresh"] = True
    yield
    with client.session_transaction() as sess:
        sess.clear()
    with app.app_context():
        _db.session.query(RideEvent).filter(RideEvent.d.like("hitchmap-rt-%")).delete(synchronize_session=False)
        _db.session.query(User).filter_by(username=USERNAME).delete()
        _db.session.commit()


def test_every_form_field_survives_save_and_edit(app, client, monkeypatch, owner):
    from hitch.extensions import db as _db
    from hitch.models import RideEvent
    from tests.conftest import TEST_PUBKEY

    _Poster.records = []
    monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _Poster)
    posted = {k: v[0] for k, v in FORM.items()}
    r = client.post("/ride", data=dict(posted, client_d_tag="rt-1"), headers={"X-Requested-With": "ride-form"})
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    record = _Poster.records[-1]

    d_tag = "hitchmap-rt-1"
    with app.app_context():
        _db.session.query(RideEvent).filter_by(d=d_tag).delete()
        # Same parser _store_published_ride and both fetch crons use, so the row's
        # extracted columns (rating, comment, ...) are what production would hold.
        fields = parse_post_to_ride_fields(
            {
                "id": "rtevt1",
                "pubkey": TEST_PUBKEY,
                "sig": "s" * 128,
                "kind": 36820,
                "created_at": 1_800_000_000,
                "tags": [["d", d_tag], ["published_at", "1800000000"]],
                "content": json.dumps(record.model_dump(mode="json", exclude_none=True)),
            }
        )
        _db.session.add(RideEvent(**fields))
        _db.session.commit()

    captured = {}
    real = main.render_template

    def spy(name, **kw):
        if name == "ride_form.html":
            captured.update(kw.get("ride_data") or {})
        return real(name, **kw)

    monkeypatch.setattr(main, "render_template", spy)
    assert client.get(f"/ride?edit={d_tag}").status_code == 200

    lost = {}
    for field, (sent, expected) in FORM.items():
        want = sent if expected is None else expected
        got = captured.get("rating" if field == "rate" else field)
        if _norm(got) != _norm(want):
            lost[field] = (want, got)
    assert not lost, f"fields lost on save->edit: {lost}"


def test_gave_up_ride_stays_gave_up_on_edit(app, client, monkeypatch, owner):
    """A 'no ride' report must reopen with its box ticked, or re-saving it turns it into a ride."""
    from hitch.extensions import db as _db
    from hitch.models import RideEvent
    from tests.conftest import TEST_PUBKEY

    _Poster.records = []
    monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _Poster)
    posted = {
        "rate": "1",
        "wait": "90",
        "pickup_lat": "52.0",
        "pickup_lon": "13.0",
        "no_ride": "1",
        "signal": "thumb",
        "comment": "",
        "destination_lat": "52.3",
        "destination_lon": "13.3",
    }
    r = client.post("/ride", data=dict(posted, client_d_tag="rt-2"), headers={"X-Requested-With": "ride-form"})
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    d_tag = "hitchmap-rt-2"
    with app.app_context():
        fields = parse_post_to_ride_fields(
            {
                "id": "rtevt2",
                "pubkey": TEST_PUBKEY,
                "sig": "s" * 128,
                "kind": 36820,
                "created_at": 1_800_000_000,
                "tags": [["d", d_tag], ["published_at", "1800000000"]],
                "content": json.dumps(_Poster.records[-1].model_dump(mode="json", exclude_none=True)),
            }
        )
        _db.session.add(RideEvent(**fields))
        _db.session.commit()
    captured = {}
    real = main.render_template

    def spy(name, **kw):
        if name == "ride_form.html":
            captured.update(kw.get("ride_data") or {})
        return real(name, **kw)

    monkeypatch.setattr(main, "render_template", spy)
    assert client.get(f"/ride?edit={d_tag}").status_code == 200
    assert captured.get("no_ride") is True
    assert float(captured.get("wait")) == 90
    assert captured.get("signal") == ["thumb"]
