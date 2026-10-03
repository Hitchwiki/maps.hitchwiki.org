"""Web Push delivery of existing in-app notifications (#292 slice 2)."""

import sys
import types

import pytest

from hitch.blueprints.utils import notifications as N
from hitch.extensions import db as _db
from hitch.models import Notification, PushSubscription, User


@pytest.fixture
def person(app):
    with app.app_context():
        user = User(username="pushrecv", email="pr@example.com", password="x", active=True, fs_uniquifier="pr-uq")
        _db.session.add(user)
        _db.session.commit()
        _db.session.add(PushSubscription(user_id=user.id, endpoint="https://push.example/1", p256dh="k", auth="a"))
        _db.session.commit()
        uid = user.id
    yield uid
    with app.app_context():
        PushSubscription.query.delete()
        Notification.query.delete()
        _db.session.delete(_db.session.get(User, uid))
        _db.session.commit()


@pytest.fixture
def fake_webpush(monkeypatch):
    calls = []
    mod = types.ModuleType("pywebpush")

    class WebPushException(Exception):
        def __init__(self, status):
            self.response = types.SimpleNamespace(status_code=status)

    mod.WebPushException = WebPushException
    mod.webpush = lambda **kw: calls.append(kw)
    monkeypatch.setitem(sys.modules, "pywebpush", mod)
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "priv")
    return calls, mod


def test_follow_alert_is_pushed_with_existing_text(app, person, fake_webpush):
    calls, _ = fake_webpush
    with app.app_context():
        N.notify_new_follower(person, "alice")
    assert len(calls) == 1
    assert "alice started following you." in calls[0]["data"]


def test_non_person_kinds_are_not_pushed(app, person, fake_webpush):
    calls, _ = fake_webpush
    with app.app_context():
        N.add_notification(person, "welcome", kind="welcome")
    assert calls == []


def test_dormant_without_private_key(app, person, fake_webpush, monkeypatch):
    calls, _ = fake_webpush
    monkeypatch.delenv("VAPID_PRIVATE_KEY")
    with app.app_context():
        N.notify_new_follower(person, "bob")
    assert calls == []


def test_gone_subscription_is_deleted(app, person, fake_webpush):
    _, mod = fake_webpush

    def gone(**kw):
        raise mod.WebPushException(410)

    mod.webpush = gone
    with app.app_context():
        N.notify_new_follower(person, "carol")
        assert PushSubscription.query.count() == 0
