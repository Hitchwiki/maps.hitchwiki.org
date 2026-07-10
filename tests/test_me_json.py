"""Tests for /me.json, the data source for the on-map account modal (issue #106)."""

import pytest

from hitch.blueprints.user import RIDES_IN_MODAL_CAP
from hitch.extensions import db as _db
from hitch.models import User


@pytest.fixture
def logged_in_user(app, client):
    """Create a user and log them in.

    Login is Hitchwiki OAuth (no local password form to POST), so seed Flask-Login's
    session key directly — the same thing login_user() ultimately does.
    """
    with app.app_context():
        user = User(
            username="testhitcher",
            email="testhitcher@example.com",
            password="x",
            active=True,
            fs_uniquifier="me-json-test-uniquifier",
            total_rides=42,
            total_distance_km=5312.44,
            total_waiting_time_min=980,
        )
        _db.session.add(user)
        _db.session.commit()
        user_id = user.id
        username = user.username

    with client.session_transaction() as sess:
        # Flask-Security's UserMixin.get_id() returns fs_uniquifier, not the PK, so that
        # is what Flask-Login stores and looks up.
        sess["_user_id"] = "me-json-test-uniquifier"
        sess["_fresh"] = True

    yield type("U", (), {"id": user_id, "username": username})

    with app.app_context():
        u = _db.session.get(User, user_id)
        if u:
            _db.session.delete(u)
            _db.session.commit()


def test_me_json_anonymous_is_200_and_logged_out(client):
    # Must not 302 to /login: fetch() would follow it and hand the modal an HTML page.
    resp = client.get("/me.json")
    assert resp.status_code == 200
    assert resp.get_json() == {"logged_in": False}


def test_me_json_is_never_publicly_cacheable(client):
    resp = client.get("/me.json")
    cache_control = resp.headers.get("Cache-Control", "")
    assert "public" not in cache_control
    assert "no-store" in cache_control


def test_me_json_logged_in_payload(client, logged_in_user):
    resp = client.get("/me.json")
    assert resp.status_code == 200
    body = resp.get_json()

    assert body["logged_in"] is True
    assert body["username"] == logged_in_user.username
    assert body["profile_url"] == "/me"

    assert set(body["insights"]) == {"rides", "distance_km", "waiting_min", "partners"}
    assert body["insights"]["rides"] == 42
    assert body["insights"]["distance_km"] == pytest.approx(5312.44)
    assert body["insights"]["waiting_min"] == 980

    assert isinstance(body["rides"], list)
    assert len(body["rides"]) <= RIDES_IN_MODAL_CAP
    assert body["rides_total"] >= len(body["rides"])
    # submission_sort_key is an internal sort artifact and must not leak to the client.
    for ride in body["rides"]:
        assert "submission_sort_key" not in ride


def test_me_json_logged_in_is_still_not_publicly_cacheable(client, logged_in_user):
    resp = client.get("/me.json")
    assert "public" not in resp.headers.get("Cache-Control", "")
    assert "no-store" in resp.headers.get("Cache-Control", "")


def test_ride_rows_carry_completion_wait_and_distance():
    """The modal's ride list needs a completion score, wait and distance per ride.

    Completion reuses the canonical ride_score weights, so a fully-detailed ride is 100%
    and one with only gender (15) + vehicle kind (10) is 25%.
    """
    from types import SimpleNamespace

    from hitch.blueprints.user import _extract_ride_info

    stops = [
        {"location": {"latitude": 48.0, "longitude": 7.0}, "waiting_duration": "PT45M"},
        {"location": {"latitude": 49.0, "longitude": 7.0}},
    ]

    def ride(**content):
        return SimpleNamespace(content=content, d="t", rating=4, comment="", submission_time="2026-07-01T12:00:00Z")

    full = ride(
        stops=stops,
        occupants=[
            {
                "was_driver": True,
                "gender": "female",
                "year_of_birth": 1980,
                "origin_country": "DE",
                "languages": ["deu"],
                "reasons_to_pick_up": ["curiosity"],
            }
        ],
        mode_of_transportation={"kind": "car", "license_plate_country": "DE"},
    )
    info = _extract_ride_info(full, "own")
    assert info["completion"] == 100
    assert info["wait_min"] == 45
    # 1 degree of latitude, scaled by show.py's 1.25 road-detour factor.
    assert info["distance_km"] == 138.9

    partial = ride(stops=stops, occupants=[{"was_driver": True, "gender": "female"}], mode_of_transportation={"kind": "car"})
    assert _extract_ride_info(partial, "own")["completion"] == 25

    # No destination and no wait recorded -> None, so the UI omits them.
    bare = _extract_ride_info(ride(stops=[stops[0] | {"waiting_duration": ""}]), "own")
    assert bare["completion"] == 0
    assert bare["wait_min"] is None
    assert bare["distance_km"] is None


def test_missing_destination_is_flagged_but_give_ups_are_not():
    """A ride with no destination is fixable data -> flag it.

    A `no_ride` record is a give-up: the hitchhiker was never picked up, so having no
    destination is correct and must not raise a false alarm.
    """
    from types import SimpleNamespace

    from hitch.blueprints.user import _extract_ride_info

    start = {"location": {"latitude": 48.0, "longitude": 7.0}}
    end = {"location": {"latitude": 49.0, "longitude": 7.0}}

    def ride(**content):
        return SimpleNamespace(content=content, d="t", rating=0, comment="", submission_time="2026-07-01T12:00:00Z")

    # Real ride, destination recorded -> no flag.
    assert _extract_ride_info(ride(stops=[start, end]), "own")["missing_destination"] is False

    # Real ride, no destination -> flag.
    assert _extract_ride_info(ride(stops=[start]), "own")["missing_destination"] is True

    # Give-up (no_ride present), no destination -> NOT flagged.
    gave_up = ride(stops=[start], no_ride={"reasons": []})
    assert _extract_ride_info(gave_up, "own")["missing_destination"] is False


def test_me_json_carries_only_earned_achievements(client, logged_in_user):
    """The modal celebrates earned tiers; locked ones stay on the /insights page.

    The fixture user has 42 rides and 5312 km, so they clear "Thumb Warmer" (5 rides),
    "Out of Town" (100 km) and "Continental Drifter" (1000 km), but not the 100-ride or
    10 000-km tiers.
    """
    body = client.get("/me.json").get_json()
    awards = body["achievements"]
    names = [a["name"] for a in awards]

    assert "Thumb Warmer" in names
    assert "Out of Town" in names
    assert "Continental Drifter" in names
    # Not yet earned -> must not appear.
    assert "Roadside Regular" not in names
    assert "Quarter Way Round the World" not in names

    for award in awards:
        assert set(award) == {"emoji", "name", "blurb"}
        assert award["emoji"] and award["name"]


def test_ride_places_lookup_is_bounded_to_the_rides_asked_for(app, db):
    """Place names come from a table, looked up by the d_tags being rendered.

    The first implementation cached the whole corpus as a JSON blob; at ~70 000 rides that
    is ~7 MB on disk and ~33 MB of parsed dict resident in *every* waitress worker, to
    answer a question about 50 rides. This pins the bounded behaviour.
    """
    from hitch.blueprints.user import _ride_places
    from hitch.models import RidePlace

    with app.app_context():
        db.session.add(RidePlace(d_tag="a", from_place="Metzeral", from_cc="FR", to_place="Mitte", to_cc="DE"))
        db.session.add(RidePlace(d_tag="b", from_place="Milano", from_cc="IT"))
        db.session.commit()

        found = _ride_places(["a", "missing"])
        # Only what was asked for, and a miss is simply absent rather than an error.
        assert set(found) == {"a"}
        assert found["a"].from_place == "Metzeral"
        assert found["a"].to_cc == "DE"

        # A ride with no destination stores only its origin.
        assert _ride_places(["b"])["b"].to_place is None

        # No d_tags -> no query at all.
        assert _ride_places([]) == {}
        assert _ride_places([None]) == {}
