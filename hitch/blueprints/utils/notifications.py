"""Simple in-app notification helpers.

Notifications are short messages shown in a user's profile. We deliberately keep only
the newest few per user (older ones are deleted on every insert) so the table stays
small and the profile only ever shows a recent, relevant list.
"""

from hitch.extensions import db
from hitch.models import Notification

# Keep at most this many notifications per user; older rows are trimmed on insert.
MAX_NOTIFICATIONS_PER_USER = 10

# The default first notification every user gets, inviting them into the two core
# social features. Kept as a constant so `ensure_welcome_notification` can dedupe on it.
WELCOME_MESSAGE = (
    "Welcome to Hitchwiki Maps! 👋 Follow other hitchhikers to see their rides on the map, "
    "and create a trip to group your own rides into a journey."
)


def add_notification(user_id, message, link=None, kind="general"):
    """Create a notification for `user_id`, then trim to the newest MAX_NOTIFICATIONS_PER_USER."""
    db.session.add(Notification(user_id=user_id, message=message, link=link, kind=kind))
    db.session.commit()
    _trim(user_id)


def _trim(user_id):
    """Delete everything beyond the newest MAX_NOTIFICATIONS_PER_USER for this user."""
    extra = (
        Notification.query.filter_by(user_id=user_id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset(MAX_NOTIFICATIONS_PER_USER)
        .all()
    )
    if extra:
        for n in extra:
            db.session.delete(n)
        db.session.commit()


def ensure_welcome_notification(user):
    """Create the one-time welcome notification for `user` if they don't have one yet.

    Idempotent: dedupes on kind='welcome', so it can be called on every login (and thus
    also back-fills users who registered before notifications existed) and still only
    ever creates the welcome once.
    """
    if user is None or user.is_anonymous:
        return
    if Notification.query.filter_by(user_id=user.id, kind="welcome").first() is None:
        add_notification(user.id, WELCOME_MESSAGE, link="/create-trip", kind="welcome")


def notify_new_follower(followed_user_id, follower_username):
    """Tell a user that `follower_username` started following them."""
    add_notification(
        followed_user_id,
        f"{follower_username} started following you.",
        link=f"/account/{follower_username}",
        kind="follow",
    )


def notify_co_hitchhiker_invite(invited_user_id, inviter_username):
    """Tell a user they were added as a co-hitchhiker on a ride and must accept/reject it."""
    add_notification(
        invited_user_id,
        f"{inviter_username} added you as a co-hitchhiker on a ride. "
        "Accept or reject it below.",
        link="/me",
        kind="co_hitchhiker",
    )


def notify_new_message(recipient_id, sender_username):
    """Tell a user they received a new chat message from `sender_username`.

    Deduped on the (kind, link) pair rather than blindly appended: while a conversation is
    unread we keep a single "new message" notification pointing at the thread and refresh
    its timestamp, so an active back-and-forth doesn't bury the bell under ten identical
    rows. Once the recipient opens the thread the notification is marked read, and the next
    message creates a fresh one.
    """
    link = f"/messages/{sender_username}"
    existing = (
        Notification.query.filter_by(user_id=recipient_id, kind="message", link=link, is_read=False)
        .order_by(Notification.created_at.desc())
        .first()
    )
    if existing is not None:
        existing.created_at = db.func.now()
        db.session.commit()
        return
    add_notification(
        recipient_id,
        f"{sender_username} sent you a message.",
        link=link,
        kind="message",
    )


def notify_nearby_hitchhikers(user_id, usernames):
    """Tell a user which other hitchhikers were logged near them recently.

    Mirrors the nearby-hitchhikers email (same trigger/gating in notify_nearby_hitchhikers.py),
    so opted-in users also get an in-app record of the encounter.
    """
    if not usernames:
        return
    names = ", ".join(usernames)
    plural = "hitchhikers were" if len(usernames) > 1 else "hitchhiker was"
    add_notification(
        user_id,
        f"{len(usernames)} {plural} logged near you recently: {names}. See their profiles on the map.",
        link="/leaderboard",
        kind="nearby",
    )


def unread_count(user):
    """Number of unread notifications for `user` (0 for anonymous/None)."""
    if user is None or user.is_anonymous:
        return 0
    return Notification.query.filter_by(user_id=user.id, is_read=False).count()
