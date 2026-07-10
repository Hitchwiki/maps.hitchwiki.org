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
