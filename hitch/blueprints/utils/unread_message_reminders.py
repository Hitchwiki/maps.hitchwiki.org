"""Second email for chat messages still unread a week after they arrived.

The first email goes out from the messages blueprint the moment a burst starts (one per
burst, see `send`). People miss it — it lands in spam, or arrives while they're on the
road — and a chat message is only worth anything if it's read, so once a week has passed
with the burst still unread we send exactly one reminder.

One reminder per (sender, recipient) unread burst, ever: every unread message in that
pair is stamped with `reminder_sent_at` when the reminder goes out, so a later message in
the same still-unread burst doesn't trigger another one. Reading the thread ends the burst;
a new message after that starts a fresh one, with its own first email and, if ignored
again, its own reminder.

Kept out of hitch/scripts/ because `flask generate` runs a script by importing it, so a
module there can't be imported by a test without sending mail.
"""

import logging
from datetime import datetime, timedelta, timezone

from hitch.blueprints.utils.send_new_message_email import send_unread_message_reminder_email
from hitch.blueprints.utils.send_welcome_email import _SYNTHETIC_EMAIL_SUFFIX
from hitch.extensions import db
from hitch.models import Message, User

logger = logging.getLogger(__name__)

REMINDER_AFTER = timedelta(days=7)
# Same length as the first email's preview (messages.EMAIL_PREVIEW_LEN); not imported
# from there to keep this module free of the blueprint's request-side imports.
PREVIEW_LEN = 140


def _preview(body):
    return body[:PREVIEW_LEN] + ("…" if len(body) > PREVIEW_LEN else "")


def remind_unread_messages(now=None):
    """Send every due reminder. Returns how many emails went out."""
    # created_at is written by SQLite's CURRENT_TIMESTAMP, i.e. naive UTC.
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now - REMINDER_AFTER

    # Pairs whose oldest un-reminded unread message is at least a week old.
    due = (
        db.session.query(Message.sender_id, Message.recipient_id)
        .filter(Message.is_read.is_(False), Message.reminder_sent_at.is_(None), Message.created_at <= cutoff)
        .distinct()
        .all()
    )

    sent = 0
    for sender_id, recipient_id in due:
        sender = db.session.get(User, sender_id)
        recipient = db.session.get(User, recipient_id)
        if sender is None or recipient is None or not recipient.active:
            continue
        # Same gates as the first email: the per-user message-email opt-in, and never a
        # synthetic OAuth address. Skipped pairs are left unstamped on purpose, so turning
        # the opt-in back on still gets the reminder.
        if not recipient.message_email_notifications:
            continue
        if not recipient.email or recipient.email.endswith(_SYNTHETIC_EMAIL_SUFFIX):
            continue

        unread = (
            Message.query.filter_by(sender_id=sender_id, recipient_id=recipient_id, is_read=False)
            .filter(Message.reminder_sent_at.is_(None))
            .order_by(Message.created_at, Message.id)
            .all()
        )
        # Preview the oldest unread message: it's the one that has been waiting a week.
        try:
            send_unread_message_reminder_email(recipient, sender.username, _preview(unread[0].body))
        except Exception:
            logger.exception("Failed to send unread-message reminder to %s", recipient.username)
            continue
        for m in unread:
            m.reminder_sent_at = now
        db.session.commit()
        sent += 1
        logger.info("Reminded %s of %d unread message(s) from %s", recipient.username, len(unread), sender.username)

    return sent
