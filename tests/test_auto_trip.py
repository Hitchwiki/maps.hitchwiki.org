"""Tests for /auto-trip — the trip the in-ride tracker auto-creates for a journey that
produced more than one ride, for signed-in and anonymous hitchhikers alike."""

import time

import pytest

import hitch.blueprints.user as user_module
from hitch.extensions import db as _db
from hitch.models import RideEvent, Trip, TripRide, User

_UNIQUIFIER = "auto-trip-test-uniquifier"


def _make_ride(d_tag, nickname, lat, lon, dest_lat, dest_lon, created_at=None, submitted="2026-07-20T10:00:00Z"):
    """A RideEvent shaped the way the Nostr parser writes them (content is what we read)."""
    stops = [{"location": {"latitude": lat, "longitude": lon}}]
    if dest_lat is not None:
        stops.append({"location": {"latitude": dest_lat, "longitude": dest_lon}})
    content = {
        "source": "maps.hitchwiki.org",
        "hitchhikers": [{"nickname": nickname}],
        "stops": stops,
    }
    return RideEvent(
        id=f"event-{d_tag}",
        kind=36820,
        pubkey="pub",
        sig="sig",
        content=content,
        created_at=int(time.time()) if created_at is None else created_at,
        d=d_tag,
        submission_time=submitted,
        stops=stops,
        hitchhikers=content["hitchhikers"],
        source="maps.hitchwiki.org",
    )


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Trip naming reverse-geocodes; tests must never depend on Photon being reachable.

    Patched to a deterministic label so the name assertions test our formatting, not a
    third party's place database.
    """
    labels = {}

    def fake_place_label(lat, lon):
        return labels.get((round(lat, 4), round(lon, 4)))

    monkeypatch.setattr(user_module, "_place_label", fake_place_label)
    return labels


@pytest.fixture
def rides(app):
    """Two anonymous rides and two belonging to `autotripper`, cleaned up afterwards."""
    with app.app_context():
        _db.session.add_all(
            [
                _make_ride("anon-1", "Anonymous", 51.05, 13.73, 51.5, 13.4),
                _make_ride("anon-2", "Anonymous", 51.5, 13.4, 52.52, 13.40),
                _make_ride("mine-1", "autotripper", 48.20, 16.37, 48.3, 16.0),
                _make_ride("mine-2", "autotripper", 48.30, 16.00, 47.07, 15.44),
                _make_ride("theirs-1", "someoneelse", 45.0, 9.0, 45.5, 9.5),
                _make_ride("theirs-2", "someoneelse", 45.5, 9.5, 46.0, 10.0),
            ]
        )
        _db.session.commit()
    yield
    with app.app_context():
        RideEvent.query.delete()
        TripRide.query.delete()
        Trip.query.delete()
        _db.session.commit()


@pytest.fixture
def logged_in(app, client):
    with app.app_context():
        user = User(
            username="autotripper",
            email="autotripper@example.com",
            password="x",
            active=True,
            fs_uniquifier=_UNIQUIFIER,
        )
        _db.session.add(user)
        _db.session.commit()
        user_id = user.id
    with client.session_transaction() as sess:
        sess["_user_id"] = _UNIQUIFIER
        sess["_fresh"] = True
    yield user_id
    with app.app_context():
        u = _db.session.get(User, user_id)
        if u:
            _db.session.delete(u)
            _db.session.commit()


def _post(client, d_tags):
    return client.post("/auto-trip", data={"ride_d_tags": ",".join(d_tags)})


# ── Creation ──────────────────────────────────────────────────────────────────


def test_creates_trip_owned_by_the_logged_in_hitchhiker(client, app, rides, logged_in):
    resp = _post(client, ["mine-1", "mine-2"])
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] and body["created"]
    with app.app_context():
        trip = _db.session.get(Trip, body["trip_id"])
        assert trip.user_id == logged_in
        assert {tr.ride_d_tag for tr in TripRide.query.filter_by(trip_id=trip.id)} == {"mine-1", "mine-2"}


def test_anonymous_journey_gets_an_ownerless_trip(client, app, rides):
    # The whole point of the nullable user_id: an anonymous multi-ride journey still
    # groups itself, and the reply carries the link that is the only way back to it.
    resp = _post(client, ["anon-1", "anon-2"])
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["url"] == f"/trip/{body['trip_id']}"
    with app.app_context():
        assert _db.session.get(Trip, body["trip_id"]).user_id is None


def test_ownerless_trip_page_renders(client, app, rides):
    trip_id = _post(client, ["anon-1", "anon-2"]).get_json()["trip_id"]
    # session.get(User, None) raises rather than returning None, so an unguarded owner
    # lookup would turn every anonymous trip page into a 500.
    assert client.get(f"/trip/{trip_id}").status_code == 200
    assert client.get(f"/trip/{trip_id}/preview.png").status_code == 200


def test_ownerless_trip_cannot_be_edited_or_deleted(client, app, rides, logged_in):
    # Built directly rather than through /auto-trip: this client is signed in, and a
    # signed-in caller cannot group anonymous rides (see the ownership tests below).
    with app.app_context():
        trip = Trip(user_id=None, name="Somewhere, July 2026")
        _db.session.add(trip)
        _db.session.commit()
        trip_id = trip.id
    # A logged-in visitor must not inherit an ownerless trip just by asking for it.
    assert client.post(f"/delete-trip/{trip_id}").headers["Location"] == "/me"
    assert client.get(f"/edit-trip/{trip_id}").headers["Location"] == "/me"
    with app.app_context():
        assert _db.session.get(Trip, trip_id) is not None


# ── Who may group what ────────────────────────────────────────────────────────


def test_rejects_rides_the_logged_in_user_is_not_on(client, rides, logged_in):
    resp = _post(client, ["theirs-1", "theirs-2"])
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_anonymous_cannot_group_attributed_rides(client, rides):
    # Anonymity means there is no identity to check, so the only rides an anonymous
    # caller may group are ones with no named hitchhiker.
    assert _post(client, ["mine-1", "mine-2"]).status_code == 400
    assert _post(client, ["anon-1", "mine-1"]).status_code == 400


def test_unknown_and_stale_rides_are_dropped(client, app, rides, logged_in):
    with app.app_context():
        old = RideEvent.query.filter_by(d="mine-2").one()
        old.created_at = int(time.time()) - user_module.AUTO_TRIP_MAX_AGE_S - 1
        _db.session.commit()
    # One ride too old and one that does not exist leaves fewer than two groupable rides.
    assert _post(client, ["mine-1", "mine-2"]).status_code == 400
    assert _post(client, ["mine-1", "does-not-exist"]).status_code == 400


def test_single_ride_is_not_a_trip(client, rides, logged_in):
    assert _post(client, ["mine-1"]).status_code == 400
    assert _post(client, ["mine-1", "mine-1"]).status_code == 400  # de-duped, so still one


# ── Idempotency ───────────────────────────────────────────────────────────────


def test_repeat_post_returns_the_same_trip(client, app, rides, logged_in):
    # The client retries this call after an offline stretch; a retry must not mint a
    # second trip holding the same rides.
    first = _post(client, ["mine-1", "mine-2"]).get_json()
    second = _post(client, ["mine-1", "mine-2"]).get_json()
    assert second["trip_id"] == first["trip_id"]
    assert second["created"] is False
    with app.app_context():
        assert Trip.query.count() == 1


def test_rides_already_in_a_manual_trip_are_left_alone(client, app, rides, logged_in):
    with app.app_context():
        trip = Trip(user_id=logged_in, name="My own name")
        _db.session.add(trip)
        _db.session.flush()
        _db.session.add(TripRide(trip_id=trip.id, ride_d_tag="mine-1"))
        _db.session.commit()
        existing_id, existing_name = trip.id, trip.name
    body = _post(client, ["mine-1", "mine-2"]).get_json()
    assert body["trip_id"] == existing_id
    with app.app_context():
        # Neither renamed nor extended: the user's own grouping wins.
        assert _db.session.get(Trip, existing_id).name == existing_name
        assert TripRide.query.filter_by(trip_id=existing_id).count() == 1


# ── Naming ────────────────────────────────────────────────────────────────────


def test_name_spans_both_ends_of_the_journey(client, app, rides, logged_in, no_network):
    no_network[(48.2, 16.37)] = "Vienna"  # first pickup
    no_network[(47.07, 15.44)] = "Graz"  # last destination
    body = _post(client, ["mine-1", "mine-2"]).get_json()
    assert body["name"] == "Vienna → Graz, July 2026"


def test_name_collapses_when_both_ends_are_the_same_place(client, rides, logged_in, no_network):
    no_network[(48.2, 16.37)] = "Vienna"
    no_network[(47.07, 15.44)] = "Vienna"
    assert _post(client, ["mine-1", "mine-2"]).get_json()["name"] == "Vienna, July 2026"


def test_name_falls_back_when_nothing_reverse_geocodes(client, rides, logged_in):
    # Photon down, or a coordinate nowhere near a settlement: still better than
    # "Untitled trip", and still dated.
    assert _post(client, ["mine-1", "mine-2"]).get_json()["name"] == "Hitchhiking trip, July 2026"


def test_place_label_returns_none_when_photon_fails(monkeypatch):
    # _place_label is patched out everywhere else, so exercise the real one here: a
    # third-party outage must degrade the name, never 500 the request.
    def boom(*args, **kwargs):
        raise user_module.requests.RequestException("down")

    monkeypatch.setattr(user_module.requests, "get", boom)
    assert user_module._place_label(51.0, 13.0) is None
