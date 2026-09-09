"""POST /feedback — the in-product feedback prompt that replaced the dead Google Form.

Anonymous submissions are allowed (the ride form itself is); an anonymous visitor may
optionally leave an email, and only a plausible one is kept. A logged-in submission
snapshots the username and never takes a typed email.
"""

import pytest

from hitch.extensions import db as _db
from hitch.models import FeedbackNote, User

_UNIQUIFIER = "feedback-test-uniquifier"


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        FeedbackNote.query.delete()
        _db.session.commit()


@pytest.fixture
def logged_in(app, client):
    with app.app_context():
        user = User(
            username="FeedbackTester",
            email="feedbacktester@example.com",
            password="x",
            active=True,
            fs_uniquifier=_UNIQUIFIER,
        )
        _db.session.add(user)
        _db.session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = _UNIQUIFIER
        sess["_fresh"] = True
    yield
    with app.app_context():
        User.query.filter_by(fs_uniquifier=_UNIQUIFIER).delete()
        _db.session.commit()


def test_anonymous_note_is_stored(app, client):
    r = client.post("/feedback", data={"note": "  the map is great  ", "context": "ride-submitted"})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    with app.app_context():
        row = FeedbackNote.query.one()
        assert row.note == "the map is great"
        assert row.context == "ride-submitted"
        assert row.user_id is None and row.username is None and row.email is None


def test_empty_note_rejected(app, client):
    r = client.post("/feedback", data={"note": "   "})
    assert r.status_code == 400
    with app.app_context():
        assert FeedbackNote.query.count() == 0


def test_unknown_context_is_dropped(app, client):
    client.post("/feedback", data={"note": "hi", "context": "bogus"})
    with app.app_context():
        assert FeedbackNote.query.one().context is None


def test_anonymous_email_kept_only_when_plausible(app, client):
    client.post("/feedback", data={"note": "a", "email": "me@example.com"})
    client.post("/feedback", data={"note": "b", "email": "not an email"})
    with app.app_context():
        rows = {row.note: row.email for row in FeedbackNote.query.all()}
        assert rows["a"] == "me@example.com"
        assert rows["b"] is None


def test_logged_in_snapshots_username_and_ignores_typed_email(app, client, logged_in):
    r = client.post("/feedback", data={"note": "logged in note", "email": "spoof@example.com"})
    assert r.status_code == 200
    with app.app_context():
        row = FeedbackNote.query.one()
        assert row.username == "FeedbackTester"
        assert row.user_id is not None
        assert row.email is None
