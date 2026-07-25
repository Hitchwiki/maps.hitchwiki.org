"""Rides logged since show.py last ran, served live so the map shows them at once."""

import json
import os

import pytest

import hitch.blueprints.main as main
from hitch.blueprints.utils.report_ride import OWNER_DELETE_REASON
from hitch.extensions import db as _db
from hitch.models import RideEvent, RideReport

PUBKEY = "a" * 64
GENERATED_TS = 1_800_000_000


def _ride(d_tag, created_at, comment="great ride", nickname="kim", lat=51.08170, lon=13.73629):
    return RideEvent(
        id=f"event-{d_tag}",
        kind=36820,
        pubkey=PUBKEY,
        sig="s" * 128,
        created_at=created_at,
        content={},
        d=d_tag,
        comment=comment,
        rating=4,
        submission_time="2026-07-02T16:35:00",
        hitchhikers=[{"nickname": nickname}] if nickname else [],
        stops=[
            {
                "location": {"latitude": lat, "longitude": lon},
                "departure_time": "2026-07-02T14:00",
                "waiting_duration": "PT12M",
            }
        ],
    )


@pytest.fixture
def dist(app, tmp_path, monkeypatch):
    """Point main.py at a throwaway dist/ and clear the ride tables around each test."""
    monkeypatch.setattr(main, "get_dirs", lambda: {"dist": str(tmp_path)})
    with app.app_context():
        _db.session.query(RideEvent).delete()
        _db.session.query(RideReport).delete()
        _db.session.commit()
    yield tmp_path
    with app.app_context():
        _db.session.query(RideEvent).delete()
        _db.session.query(RideReport).delete()
        _db.session.commit()


def _write_generated_at(dist, ts=GENERATED_TS):
    (dist / "generated_at.json").write_text(json.dumps({"ts": ts}))


def _add(app, *rides):
    with app.app_context():
        for ride in rides:
            _db.session.add(ride)
        _db.session.commit()


class TestCutoff:
    def test_a_ride_older_than_the_last_generation_is_not_pending(self, app, client, dist):
        _write_generated_at(dist)
        _add(app, _ride("old", GENERATED_TS - 60))
        assert client.get("/pending_rides.json").get_json() == []

    def test_a_ride_logged_since_the_last_generation_is_pending(self, app, client, dist):
        _write_generated_at(dist)
        _add(app, _ride("fresh", GENERATED_TS + 60))
        payload = client.get("/pending_rides.json").get_json()
        assert [entry["id"] for entry in payload] == ["fresh"]
        assert payload[0]["spot_id"] == "51.08170_13.73629"
        assert payload[0]["wait"] == 12

    def test_falls_back_to_the_rides_index_mtime(self, app, client, dist):
        # Before the first show.py run that writes generated_at.json. The index mtime is
        # LATER than the snapshot it was built from, so this under-returns rather than
        # over-returns: worst case a ride waits for the cron, as it does today.
        index = dist / "rides_index.json"
        index.write_text("[]")
        os.utime(index, (GENERATED_TS, GENERATED_TS))
        _add(app, _ride("old", GENERATED_TS - 60), _ride("fresh", GENERATED_TS + 60))
        assert [e["id"] for e in client.get("/pending_rides.json").get_json()] == ["fresh"]

    def test_no_generated_data_at_all_yields_nothing(self, app, client, dist):
        _add(app, _ride("fresh", GENERATED_TS + 60))
        assert client.get("/pending_rides.json").get_json() == []


class TestExclusions:
    def test_an_owner_deleted_ride_is_withheld(self, app, client, dist):
        # It would otherwise reappear on the map for ten minutes after being hidden.
        _write_generated_at(dist)
        _add(app, _ride("fresh", GENERATED_TS + 60))
        with app.app_context():
            _db.session.add(RideReport(ride_d_tag="fresh", user_id=1, reason=OWNER_DELETE_REASON))
            _db.session.commit()
        assert client.get("/pending_rides.json").get_json() == []

    def test_two_reports_for_the_same_reason_hide_the_ride(self, app, client, dist):
        _write_generated_at(dist)
        _add(app, _ride("fresh", GENERATED_TS + 60))
        with app.app_context():
            _db.session.add(RideReport(ride_d_tag="fresh", user_id=1, reason="spam"))
            _db.session.add(RideReport(ride_d_tag="fresh", user_id=2, reason="spam"))
            _db.session.commit()
        assert client.get("/pending_rides.json").get_json() == []

    def test_a_single_report_does_not(self, app, client, dist):
        _write_generated_at(dist)
        _add(app, _ride("fresh", GENERATED_TS + 60))
        with app.app_context():
            _db.session.add(RideReport(ride_d_tag="fresh", user_id=1, reason="spam"))
            _db.session.commit()
        assert [e["id"] for e in client.get("/pending_rides.json").get_json()] == ["fresh"]

    def test_an_anonymous_rating_only_ride_is_withheld(self, app, client, dist):
        _write_generated_at(dist)
        ride = _ride("fresh", GENERATED_TS + 60, comment=None, nickname=None)
        ride.stops[0].pop("waiting_duration")
        _add(app, ride)
        assert client.get("/pending_rides.json").get_json() == []
