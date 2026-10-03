"""Web Push subscription endpoints (#292 slice 1): opt-in storage, dormant without a VAPID key."""

import pytest

from hitch.extensions import db as _db
from hitch.models import PushSubscription, User

_UNIQUIFIER = "push-test-uniquifier"
SUB = {"endpoint": "https://push.example.com/abc", "keys": {"p256dh": "BPkey", "auth": "authkey"}}


@pytest.fixture
def viewer(app):
    with app.app_context():
        user = User(username="pushviewer", email="pv@example.com", password="x", active=True, fs_uniquifier=_UNIQUIFIER)
        _db.session.add(user)
        _db.session.commit()
        uid = user.id
    yield uid
    with app.app_context():
        PushSubscription.query.delete()
        _db.session.delete(_db.session.get(User, uid))
        _db.session.commit()


@pytest.fixture
def login(client):
    with client.session_transaction() as sess:
        sess["_user_id"] = _UNIQUIFIER
        sess["_fresh"] = True


@pytest.fixture
def vapid(monkeypatch):
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "test-public-key")


def test_anonymous_cannot_subscribe(client, vapid):
    assert client.post("/push/subscribe", json=SUB).status_code == 401


def test_dormant_without_vapid_key(client, viewer, login, monkeypatch):
    monkeypatch.delenv("VAPID_PUBLIC_KEY", raising=False)
    assert client.post("/push/subscribe", json=SUB).status_code == 404


def test_subscribe_stores_once_and_updates(client, app, viewer, login, vapid):
    assert client.post("/push/subscribe", json=SUB).status_code == 200
    assert client.post("/push/subscribe", json={**SUB, "keys": {"p256dh": "new", "auth": "a2"}}).status_code == 200
    with app.app_context():
        rows = PushSubscription.query.all()
        assert len(rows) == 1 and rows[0].p256dh == "new" and rows[0].user_id == viewer


@pytest.mark.parametrize(
    "bad",
    [{}, {"endpoint": "http://x.example/a", "keys": SUB["keys"]}, {"endpoint": SUB["endpoint"], "keys": {}}],
)
def test_rejects_malformed(client, viewer, login, vapid, bad):
    assert client.post("/push/subscribe", json=bad).status_code == 400


def test_unsubscribe_removes_own_subscription(client, app, viewer, login, vapid):
    client.post("/push/subscribe", json=SUB)
    assert client.post("/push/unsubscribe", json={"endpoint": SUB["endpoint"]}).status_code == 200
    with app.app_context():
        assert PushSubscription.query.count() == 0
