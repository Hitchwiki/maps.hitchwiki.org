"""Tests for /auto-trip — the trip the in-ride tracker auto-creates for a journey that
produced more than one ride, for signed-in and anonymous hitchhikers alike."""

import time

import pytest

import hitch.blueprints.user as user_module
from hitch.extensions import db as _db
from hitch.models import RideEvent, Trip, TripRide, User

_UNIQUIFIER = "auto-trip-test-uniquifier"


def _make_ride(
    d_tag,
    nickname,
    lat,
    lon,
    dest_lat,
    dest_lon,
    created_at=None,
    submitted="2026-07-20T10:00:00Z",
    departed="2026-07-18T09:00:00Z",
):
    """A RideEvent shaped the way the Nostr parser writes them (content is what we read).

    `departed` is the first stop's departure_time — the ride's start time, which is what
    trips are ordered by and what a ride needs before it may join one. Pass None to build
    a ride that never recorded when it happened.
    """
    stops = [{"location": {"latitude": lat, "longitude": lon}}]
    if departed:
        stops[0]["departure_time"] = departed
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
                # Departure times ascend with the legs, as they do on a real journey.
                _make_ride("anon-1", "Anonymous", 51.05, 13.73, 51.5, 13.4, departed="2026-07-18T09:00:00Z"),
                _make_ride("anon-2", "Anonymous", 51.5, 13.4, 52.52, 13.40, departed="2026-07-18T13:00:00Z"),
                _make_ride("mine-1", "autotripper", 48.20, 16.37, 48.3, 16.0, departed="2026-07-18T09:00:00Z"),
                _make_ride("mine-2", "autotripper", 48.30, 16.00, 47.07, 15.44, departed="2026-07-18T14:00:00Z"),
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


# ── Start time (what a trip is ordered by) ────────────────────────────────────


def test_ride_without_a_start_time_cannot_be_grouped(client, app, rides, logged_in):
    # A trip is ordered and drawn by each ride's start time, so a ride that never
    # recorded one has no place in the sequence. Dropping it leaves one ride, which is
    # not a trip — a 400 the client treats as permanent rather than retrying forever.
    with app.app_context():
        undated = RideEvent.query.filter_by(d="mine-2").one()
        stops = [{k: v for k, v in stop.items() if k != "departure_time"} for stop in undated.content["stops"]]
        undated.content = {**undated.content, "stops": stops}
        undated.stops = stops
        _db.session.commit()
    assert _post(client, ["mine-1", "mine-2"]).status_code == 400
    with app.app_context():
        assert Trip.query.count() == 0


def test_trip_rides_are_ordered_by_start_time_not_submission(client, app, rides, logged_in):
    # The legs were typed up in the wrong order (mine-2 submitted first), which is exactly
    # what ordering by submission_time used to get wrong: the trip has to read in the
    # order it was hitched.
    with app.app_context():
        first, second = RideEvent.query.filter_by(d="mine-1").one(), RideEvent.query.filter_by(d="mine-2").one()
        first.submission_time, second.submission_time = "2026-07-20T18:00:00Z", "2026-07-20T09:00:00Z"
        _db.session.commit()
    trip_id = _post(client, ["mine-1", "mine-2"]).get_json()["trip_id"]
    with app.app_context():
        # Both the list and the route line read first leg → last leg.
        ordered = user_module._rides_for_trip(trip_id)
        assert [r["d_tag"] for r in ordered] == ["mine-1", "mine-2"]
        points = user_module._trip_route_points(ordered)
        assert points[0] == {"lat": 48.20, "lon": 16.37}
        assert points[-1] == {"lat": 47.07, "lon": 15.44}


def test_undated_rides_are_not_offered_by_the_trip_builder(client, app, rides, logged_in):
    with app.app_context():
        undated = RideEvent.query.filter_by(d="mine-2").one()
        stops = [{k: v for k, v in stop.items() if k != "departure_time"} for stop in undated.content["stops"]]
        undated.content = {**undated.content, "stops": stops}
        undated.stops = stops
        _db.session.commit()
    page = client.get("/create-trip").get_data(as_text=True)
    assert 'value="mine-1"' in page
    assert 'value="mine-2"' not in page
    assert "no start time" in page
    # And a hand-rolled POST can't smuggle it in either.
    client.post("/save-trip", data={"name": "Typed by hand", "ride_d_tags": ["mine-1", "mine-2"]})
    with app.app_context():
        assert {tr.ride_d_tag for tr in TripRide.query.all()} == {"mine-1"}


def test_a_legacy_undated_member_sorts_last_not_first(client, app, rides, logged_in):
    # Rides added to a trip before the start-time rule may have none. The list now reads
    # oldest first, so an undated ride must trail the sequence rather than take the top
    # slot and claim to be the first leg.
    with app.app_context():
        undated = RideEvent.query.filter_by(d="mine-1").one()
        stops = [{k: v for k, v in stop.items() if k != "departure_time"} for stop in undated.content["stops"]]
        undated.content = {**undated.content, "stops": stops}
        undated.stops = stops
        trip = Trip(user_id=logged_in, name="Legacy trip")
        _db.session.add(trip)
        _db.session.flush()
        _db.session.add_all([TripRide(trip_id=trip.id, ride_d_tag=d) for d in ("mine-1", "mine-2")])
        _db.session.commit()
        assert [r["d_tag"] for r in user_module._rides_for_trip(trip.id)] == ["mine-2", "mine-1"]


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
