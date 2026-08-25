"""Tests for the trip builder's "Why are you hitchhiking?" picker.

Stating a motive once for a journey writes it onto every ride in that journey. The rule
is **union**: a ride that recorded a reason of its own keeps it, and a reason dropped from
the trip is not stripped from the rides. Those two are the whole feature — a replacement
would quietly erase what a hitchhiker wrote on an individual ride.
"""

import time

import pytest

import hitch.blueprints.user as user_module
from hitch.extensions import db as _db
from hitch.models import RideEvent, Trip, TripRide, User

from .conftest import TEST_PUBKEY

_UNIQUIFIER = "trip-reasons-test-uniquifier"


def _make_ride(d_tag, nickname, reasons=None, co_hitchhiker=None):
    """A ride owned by `nickname`, optionally already stating its own reasons.

    Stamped with our test pubkey and the `d`/`published_at` tags, because a ride is only
    republishable when we could replace the original event (ride_sources.ride_is_replaceable)
    — an unsigned fixture would be skipped and every assertion here would pass vacuously.
    """
    hitchhikers = [{"nickname": nickname}]
    if reasons is not None:
        hitchhikers[0]["reasons_to_hitchhike"] = list(reasons)
    if co_hitchhiker:
        hitchhikers.append(co_hitchhiker)
    stops = [{"location": {"latitude": 51.05, "longitude": 13.73, "is_exact": True}, "departure_time": "2026-07-18T09:00:00Z"}]
    content = {
        "version": "0.0.0",
        "source": "maps.hitchwiki.org",
        "license": "odbl",
        "hitchhikers": hitchhikers,
        "stops": stops,
    }
    return RideEvent(
        id=f"event-{d_tag}",
        kind=36820,
        pubkey=TEST_PUBKEY,
        sig="sig",
        content=content,
        created_at=int(time.time()),
        d=d_tag,
        submission_time="2026-07-20T10:00:00Z",
        stops=stops,
        hitchhikers=hitchhikers,
        source="maps.hitchwiki.org",
        tags=[["d", d_tag], ["published_at", "1800000000"]],
    )


class _StubPoster:
    """Captures what would go to the relays instead of publishing it.

    It also writes the published record back into `ride_event`, which is what
    `store_published_ride` does for real after every publish. Without that the stored ride
    would still lack the reason it was just given, and a second save would republish it
    forever — the very thing the idempotence test is here to catch.
    """

    published = []

    def __init__(self):
        self.last_event = None

    def post(self, ride_record=None, tags=None, wait=True):
        d_tag = next((t[1] for t in (tags or []) if t[0] == "d"), None)
        type(self).published.append((d_tag, [h.reasons_to_hitchhike for h in ride_record.hitchhikers], wait))
        row = RideEvent.query.filter_by(d=d_tag).first()
        if row is not None:
            row.content = ride_record.model_dump(exclude_none=True)
            _db.session.commit()
        return d_tag

    def flush(self):
        type(self).published.append("flush")

    def close(self):
        pass


@pytest.fixture
def hitchhiker(app):
    """A logged-in user with three rides, one of which already states its own reason."""
    with app.app_context():
        user = User(
            username="tripreasoner",
            email="tripreasoner@example.invalid",
            password="x",
            active=True,
            fs_uniquifier=_UNIQUIFIER,
        )
        _db.session.add(user)
        _db.session.add_all(
            [
                _make_ride("tr-1", "tripreasoner"),
                _make_ride("tr-2", "tripreasoner", reasons=["sport"]),
                # A co-hitchhiker's own entry must never be written to: their reasons for
                # being in that car are theirs to state.
                _make_ride("tr-3", "tripreasoner", co_hitchhiker={"nickname": "someoneelse"}),
                _make_ride("tr-other", "someoneelse"),
            ]
        )
        _db.session.commit()
        yield user
        RideEvent.query.filter(RideEvent.d.in_(["tr-1", "tr-2", "tr-3", "tr-other"])).delete(synchronize_session=False)
        TripRide.query.delete()
        Trip.query.delete()
        User.query.filter_by(fs_uniquifier=_UNIQUIFIER).delete()
        _db.session.commit()


@pytest.fixture(autouse=True)
def stub_poster(monkeypatch):
    _StubPoster.published = []
    monkeypatch.setattr(user_module, "HitchhikingDataStandardToNostrPoster", _StubPoster)
    monkeypatch.setattr(user_module, "store_published_ride", lambda event: None)
    return _StubPoster


def _login(client, user):
    with client.session_transaction() as session:
        session["_user_id"] = user.fs_uniquifier
        session["_fresh"] = True


class TestUnion:
    def test_a_rides_own_reasons_survive_the_trips(self, app, client, hitchhiker, stub_poster):
        _login(client, hitchhiker)
        response = client.post(
            "/save-trip",
            data={"name": "Balkans", "reasons_to_hitchhike": "vacation,errands", "ride_d_tags": ["tr-1", "tr-2"]},
        )
        assert response.status_code == 302

        published = {e[0]: e[1] for e in stub_poster.published if isinstance(e, tuple)}
        assert published["tr-1"][0] == ["vacation", "errands"]
        # The union, in the ride's own order first: "sport" is not lost, not moved.
        assert published["tr-2"][0] == ["sport", "vacation", "errands"]

    def test_a_co_hitchhikers_entry_is_left_alone(self, app, client, hitchhiker, stub_poster):
        _login(client, hitchhiker)
        client.post("/save-trip", data={"name": "T", "reasons_to_hitchhike": "vacation", "ride_d_tags": ["tr-3"]})

        published = {e[0]: e[1] for e in stub_poster.published if isinstance(e, tuple)}
        assert published["tr-3"] == [["vacation"], None]

    def test_removing_a_reason_from_the_trip_leaves_the_rides_unchanged(self, app, client, hitchhiker, stub_poster):
        _login(client, hitchhiker)
        client.post("/save-trip", data={"name": "T", "reasons_to_hitchhike": "vacation", "ride_d_tags": ["tr-1"]})
        trip_id = Trip.query.filter_by(name="T").first().id
        stub_poster.published = []

        # Same trip, saved again with nothing ticked: the rides are the record of what
        # happened, so nothing is republished and nothing is taken off them.
        client.post("/save-trip", data={"trip_id": trip_id, "name": "T", "reasons_to_hitchhike": "", "ride_d_tags": ["tr-1"]})

        assert stub_poster.published == []
        assert _db.session.get(Trip, trip_id).reasons_to_hitchhike is None

    def test_saying_the_same_thing_twice_republishes_nothing(self, app, client, hitchhiker, stub_poster):
        _login(client, hitchhiker)
        data = {"name": "T", "reasons_to_hitchhike": "vacation", "ride_d_tags": ["tr-1"]}
        client.post("/save-trip", data=data)
        trip_id = Trip.query.filter_by(name="T").first().id
        # The first save wrote the reason into the ride, so the second has nothing to add.
        # (Publishing anyway would bump every ride's created_at and flood the relay.)
        stub_poster.published = []

        client.post("/save-trip", data={**data, "trip_id": trip_id})

        assert stub_poster.published == []


class TestWhatIsStored:
    def test_the_trip_keeps_its_reasons_so_the_picker_can_show_them(self, app, client, hitchhiker):
        _login(client, hitchhiker)
        client.post("/save-trip", data={"name": "T", "reasons_to_hitchhike": "vacation,errands"})

        trip = Trip.query.filter_by(name="T").first()
        assert trip.reasons_to_hitchhike == "vacation,errands"
        assert 'value="vacation,errands"' in client.get(f"/edit-trip/{trip.id}").get_data(as_text=True)

    def test_a_code_outside_the_enum_is_dropped(self, app, client, hitchhiker, stub_poster):
        _login(client, hitchhiker)
        # Only a crafted POST can produce this (the UI is a chip picker), and the trip is
        # still worth saving — but nothing outside the standard's vocabulary may reach a ride.
        client.post("/save-trip", data={"name": "T", "reasons_to_hitchhike": "vacation,../etc", "ride_d_tags": ["tr-1"]})

        assert Trip.query.filter_by(name="T").first().reasons_to_hitchhike == "vacation"
        published = {e[0]: e[1] for e in stub_poster.published if isinstance(e, tuple)}
        assert published["tr-1"][0] == ["vacation"]

    def test_someone_elses_ride_cannot_be_written_to(self, app, client, hitchhiker, stub_poster):
        _login(client, hitchhiker)
        # save_trip already filters membership to the user's own rides; this is the second
        # guard, in the republish itself — nothing is posted for a ride they aren't on.
        client.post("/save-trip", data={"name": "T", "reasons_to_hitchhike": "vacation", "ride_d_tags": ["tr-other"]})

        assert stub_poster.published == []
        assert TripRide.query.count() == 0


class TestBatching:
    def test_the_relay_pause_is_paid_once_per_save_not_once_per_ride(self, app, client, hitchhiker, stub_poster):
        # post(wait=True) sleeps 5 s to let the relays answer. Paying that per ride would
        # hold a twenty-ride trip's save for a minute and a half, so the batch waits once.
        _login(client, hitchhiker)
        client.post(
            "/save-trip",
            data={"name": "T", "reasons_to_hitchhike": "vacation", "ride_d_tags": ["tr-1", "tr-2", "tr-3"]},
        )

        waits = [entry[2] for entry in stub_poster.published if isinstance(entry, tuple)]
        assert waits == [False, False, False]
        assert stub_poster.published[-1] == "flush"
