"""The second email for a chat burst still unread a week later (unread_message_reminders)."""

from datetime import datetime, timedelta

import pytest

import hitch.blueprints.utils.unread_message_reminders as umr
from hitch.extensions import db as _db
from hitch.models import Message, User

NOW = datetime(2026, 10, 5, 10, 0, 0)


def _user(username, **kw):
    return User(
        username=username,
        email=kw.pop("email", f"{username.lower()}@example.com"),
        password="x",
        active=True,
        fs_uniquifier=f"uq-reminder-{username}",
        **kw,
    )


@pytest.fixture
def sent(app, monkeypatch):
    """Capture reminders instead of mailing them; clean up rows afterwards."""
    calls = []
    monkeypatch.setattr(umr, "send_unread_message_reminder_email", lambda r, s, p: calls.append((r.username, s, p)))
    with app.app_context():
        yield calls
        _db.session.rollback()
        Message.query.delete()
        User.query.filter(User.fs_uniquifier.like("uq-reminder-%")).delete(synchronize_session=False)
        _db.session.commit()


def _pair(**recipient_kw):
    sender, recipient = _user("RemSender"), _user("RemRecipient", **recipient_kw)
    _db.session.add_all([sender, recipient])
    _db.session.commit()
    return sender, recipient


def _msg(sender, recipient, body, age, is_read=False):
    m = Message(sender_id=sender.id, recipient_id=recipient.id, body=body, is_read=is_read, created_at=NOW - age)
    _db.session.add(m)
    _db.session.commit()
    return m


def test_week_old_unread_burst_gets_exactly_one_reminder(sent):
    s, r = _pair()
    first = _msg(s, r, "hello", timedelta(days=8))
    later = _msg(s, r, "are you there?", timedelta(days=2))

    assert umr.remind_unread_messages(NOW) == 1
    # Previews the message that has been waiting, and covers the whole burst.
    assert sent == [("RemRecipient", "RemSender", "hello")]
    assert first.reminder_sent_at == NOW and later.reminder_sent_at == NOW

    # Next day: nothing new to remind about, even though the burst is still unread.
    assert umr.remind_unread_messages(NOW + timedelta(days=1)) == 0
    assert len(sent) == 1


def test_not_yet_a_week_or_already_read_is_left_alone(sent):
    s, r = _pair()
    _msg(s, r, "fresh", timedelta(days=6))
    _msg(s, r, "read long ago", timedelta(days=30), is_read=True)

    assert umr.remind_unread_messages(NOW) == 0
    assert sent == []


@pytest.mark.parametrize(
    "recipient_kw",
    [{"message_email_notifications": False}, {"email": "x@hitchwiki.oauth"}],
)
def test_opted_out_or_synthetic_address_gets_no_reminder(sent, recipient_kw):
    s, r = _pair(**recipient_kw)
    m = _msg(s, r, "hello", timedelta(days=8))

    assert umr.remind_unread_messages(NOW) == 0
    # Left unstamped, so re-enabling the opt-in still delivers the reminder.
    assert m.reminder_sent_at is None


def test_failed_send_is_retried_next_run(sent, monkeypatch):
    s, r = _pair()
    m = _msg(s, r, "hello", timedelta(days=8))

    def boom(*a):
        raise RuntimeError("sparkpost down")

    monkeypatch.setattr(umr, "send_unread_message_reminder_email", boom)
    assert umr.remind_unread_messages(NOW) == 0
    assert m.reminder_sent_at is None


def test_reminder_email_is_tagged_and_worded(app, monkeypatch):
    import hitch.blueprints.utils.send_welcome_email as swe
    from hitch.blueprints.utils.send_new_message_email import send_unread_message_reminder_email

    captured = {}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {}

    def fake_post(url, headers, json, timeout):
        captured.update(json)
        return _Resp()

    monkeypatch.setattr(swe.requests, "post", fake_post)
    recipient = User(username="Chris", email="c@example.com")
    with app.app_context():
        send_unread_message_reminder_email(recipient, "Jurobola", "hi")
    assert captured["campaign_id"] == "unread-message-reminder"
    assert "still unread" in captured["content"]["text"]
