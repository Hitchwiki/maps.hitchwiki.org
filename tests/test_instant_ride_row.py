"""A submitted ride must be in the local DB — and so on its own page — immediately."""

import json

import pytest

import hitch.blueprints.main as main
from hitch.extensions import db as _db
from hitch.models import RideEvent

PUBKEY = "a" * 64


class _StubEvent:
    """Stands in for a signed pynostr Event: only `to_dict()` is used."""

    def __init__(self, raw):
        self._raw = raw

    def to_dict(self):
        return self._raw


def _raw_event(d_tag="maps.hitchwiki.org-abc", created_at=1_800_000_000, event_id="e1", comment="great ride"):
    content = {
        "version": "1.0.0",
        "source": "maps.hitchwiki.org",
        "comment": comment,
        "rating": 4,
        "submission_time": "2026-07-02T16:35:00",
        "hitchhikers": [{"nickname": "kim"}],
        "stops": [
            {
                "location": {"latitude": 51.08170, "longitude": 13.73629},
                "departure_time": "2026-07-02T14:00",
                "waiting_duration": "PT12M",
            },
            {"location": {"latitude": 52.51739, "longitude": 13.39513}, "arrival_time": "2026-07-02T16:30"},
        ],
    }
    return {
        "id": event_id,
        "kind": 36820,
        "pubkey": PUBKEY,
        "sig": "s" * 128,
        "created_at": created_at,
        "content": json.dumps(content),
        "tags": [["d", d_tag], ["published_at", str(created_at)]],
    }


def _boom_ride_event(**kwargs):
    """Stand-in for the `RideEvent` constructor used by `_store_published_ride`'s insert
    branch. Raising here drives a genuine DB-layer exception through the function's
    except/rollback path — unlike a parse failure, which returns before ever reaching it."""
    raise RuntimeError("boom")


class _RecordingPoster:
    """Fake poster that publishes nothing but exposes a signed-looking event."""

    def __init__(self):
        self.last_event = None

    def post(self, ride_record, tags=None, d_tag=None):
        tag = "maps.hitchwiki.org-abc"
        if tags is not None:
            tag = next(t[1] for t in tags if t[0] == "d")
        self.last_event = _StubEvent(_raw_event(d_tag=tag))
        return tag

    def close(self):
        pass


@pytest.fixture
def clean_rides(app):
    with app.app_context():
        _db.session.query(RideEvent).delete()
        _db.session.commit()
        yield
        _db.session.query(RideEvent).delete()
        _db.session.commit()


class TestStorePublishedRide:
    def test_inserts_a_brand_new_ride(self, app, clean_rides):
        with app.app_context():
            main._store_published_ride(_StubEvent(_raw_event()))
            row = _db.session.query(RideEvent).filter_by(d="maps.hitchwiki.org-abc").one()
            assert row.rating == 4
            assert row.comment == "great ride"

    def test_reapplying_the_same_event_is_a_no_op(self, app, clean_rides):
        # The 5-minute incremental fetch will hand us back our own event; it must not
        # duplicate the ride or change anything.
        with app.app_context():
            main._store_published_ride(_StubEvent(_raw_event()))
            main._store_published_ride(_StubEvent(_raw_event()))
            rows = _db.session.query(RideEvent).filter_by(d="maps.hitchwiki.org-abc").all()
            assert len(rows) == 1

    def test_an_edit_overwrites_the_row_including_its_primary_key(self, app, clean_rides):
        # A kind-36820 edit reuses (pubkey, d) but is a new event id, so the row is
        # replaced in place rather than added alongside.
        with app.app_context():
            main._store_published_ride(_StubEvent(_raw_event(event_id="e1", created_at=1_800_000_000)))
            main._store_published_ride(_StubEvent(_raw_event(event_id="e2", created_at=1_800_000_500, comment="rewritten")))
            rows = _db.session.query(RideEvent).filter_by(d="maps.hitchwiki.org-abc").all()
            assert len(rows) == 1
            assert rows[0].id == "e2"
            assert rows[0].comment == "rewritten"

    def test_an_unparseable_event_is_skipped(self, app, clean_rides):
        # parse_post_to_ride_fields returns None for content that isn't valid JSON, so
        # this only proves the early `return` — not the except/rollback path below it.
        # See test_a_db_error_during_storage_never_breaks_the_submit_... for that.
        with app.app_context():
            main._store_published_ride(_StubEvent({"not": "an event"}))
            assert _db.session.query(RideEvent).count() == 0

    def test_a_db_error_during_storage_never_breaks_the_submit_and_leaves_the_session_usable(self, app, clean_rides, monkeypatch):
        # The ride is already on the relay at this point; a local storage failure must
        # not turn a successful publish into a 500. Unlike the parse-failure test above,
        # this raises from inside the try block so the except/rollback path is actually
        # exercised.
        with app.app_context():
            monkeypatch.setattr(main, "RideEvent", _boom_ride_event)

            main._store_published_ride(_StubEvent(_raw_event()))

            assert _db.session.query(RideEvent).count() == 0

            # The rollback must leave the session usable for whatever write follows in
            # the real handler (CoHitchhiker rows are committed right after this call).
            probe = RideEvent(
                id="usable-check",
                kind=36820,
                pubkey=PUBKEY,
                sig="s" * 128,
                content={},
                created_at=1,
                d="usable-check-d",
            )
            _db.session.add(probe)
            _db.session.commit()
            assert _db.session.query(RideEvent).filter_by(d="usable-check-d").one().id == "usable-check"

    def test_no_event_is_tolerated(self, app, clean_rides):
        with app.app_context():
            main._store_published_ride(None)
            assert _db.session.query(RideEvent).count() == 0


class TestRideIsLiveAfterSubmit:
    def test_the_ride_page_resolves_straight_after_the_post(self, client, monkeypatch, clean_rides):
        monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _RecordingPoster)
        assert client.get("/ride/maps.hitchwiki.org-abc").status_code == 404

        resp = client.post(
            "/ride",
            data={
                "rate": "4",
                "wait": "12",
                "signal": "thumb",
                "comment": "great ride",
                "pickup_lat": "51.08170",
                "pickup_lon": "13.73629",
                "destination_lat": "52.51739",
                "destination_lon": "13.39513",
            },
            headers={"X-Requested-With": "inride"},
        )
        assert resp.status_code == 200

        assert client.get("/ride/maps.hitchwiki.org-abc").status_code == 200


class TestStorageFailureNeverBreaksTheSubmit:
    def test_endpoint_still_returns_ok_when_local_storage_fails(self, app, client, monkeypatch, clean_rides):
        # A local DB failure while storing the just-published ride must not surface as a
        # 500, and must not look like a transient relay failure (503) either — the ride
        # *was* published successfully; only our local mirror of it failed to write.
        monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _RecordingPoster)
        monkeypatch.setattr(main, "RideEvent", _boom_ride_event)

        resp = client.post(
            "/ride",
            data={
                "rate": "4",
                "wait": "12",
                "signal": "thumb",
                "comment": "great ride",
                "pickup_lat": "51.08170",
                "pickup_lon": "13.73629",
                "destination_lat": "52.51739",
                "destination_lon": "13.39513",
            },
            headers={"X-Requested-With": "inride"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

        with app.app_context():
            assert _db.session.query(RideEvent).filter_by(d="maps.hitchwiki.org-abc").count() == 0


class TestSuccessRedirectCarriesTheDTag:
    def test_a_new_ride_redirects_with_its_d_tag(self, client, monkeypatch, clean_rides):
        # The full-page POST navigates away, so the redirect URL is the only channel
        # through which the success overlay can learn the ride's permalink.
        monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _RecordingPoster)
        resp = client.post(
            "/ride",
            data={
                "rate": "4",
                "wait": "12",
                "signal": "thumb",
                "comment": "great ride",
                "pickup_lat": "51.08170",
                "pickup_lon": "13.73629",
                "destination_lat": "",
                "destination_lon": "",
            },
        )
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/?ride=maps.hitchwiki.org-abc#success-anon"
