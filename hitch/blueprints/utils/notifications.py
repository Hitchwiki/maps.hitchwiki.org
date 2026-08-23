"""Simple in-app notification helpers.

Notifications are short messages shown in a user's profile. We deliberately keep only
the newest few per user (older ones are deleted on every insert) so the table stays
small and the profile only ever shows a recent, relevant list.
"""

import json
import os

from sqlalchemy import func

from hitch.extensions import db
from hitch.models import Notification, User
from hitch.usernames import username_key

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
        f"{inviter_username} added you as a co-hitchhiker on a ride. Accept or reject it below.",
        link="/me",
        kind="co_hitchhiker",
    )


def notify_ride_like(owner_id, liker_username, ride_d_tag):
    """Tell a user that `liker_username` liked one of their rides — at most once per ride.

    Only the *first* like on a ride is worth telling someone about: with a 10-row window
    per user, a ride that catches on would otherwise evict every other notification one
    liker at a time. The caller only calls this for the first like; the dedupe on
    (kind, link) here additionally covers unlike-then-relike, which would otherwise make
    that first-like test true a second time.
    """
    link = f"/ride/{ride_d_tag}"
    if Notification.query.filter_by(user_id=owner_id, kind="ride_like", link=link).first() is not None:
        return
    add_notification(
        owner_id,
        f"{liker_username} liked your ride.",
        link=link,
        kind="ride_like",
    )


def notify_ride_comment(owner_id, commenter_username, ride_d_tag):
    """Tell a user that `commenter_username` commented on one of their rides."""
    add_notification(
        owner_id,
        f"{commenter_username} commented on your ride.",
        link=f"/ride/{ride_d_tag}#comments",
        kind="ride_comment",
    )


def notify_race_podium(user_id, race_title, position):
    """Tell a user they made the top 3 of a race (see RACES.md).

    Sent when someone *enters* the podium, not every time show.py rebuilds the standings:
    the caller diffs the new podium against the previous races.json, and the dedupe here
    catches the case where a user drops off and climbs back on. Moving up within the top 3
    is deliberately silent — the ask was to be told you're on the board, not to get a
    running commentary.
    """
    medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(position, "🏁")
    # Dedupe on the race, not the exact message: the position is part of the text, so an
    # equality check would let a 3rd -> 2nd -> 3rd wobble notify twice for one race.
    already = (
        Notification.query.filter_by(user_id=user_id, kind="race_podium")
        .filter(Notification.message.like(f"%{race_title}%"))
        .first()
    )
    if already is not None:
        return
    add_notification(
        user_id,
        f"{medal} You entered the top 3 of {race_title} — currently #{position}.",
        link="/races",
        kind="race_podium",
    )


def load_race_podiums(path):
    """{race name: [hitchhiker names, in podium order]} from an existing races.json.

    Returns None when there is no previous file — `notify_new_race_podiums` then notifies
    nobody, so a first-ever build (or a deleted races.json) can't fire off a burst of
    "you entered the top 3" for podiums that have stood for weeks.
    """
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            races = json.load(f)
    except (OSError, ValueError):
        return None
    return {r.get("name"): [ent.get("hitchhiker_name") for ent in (r.get("entries") or [])] for r in races}


def notify_new_race_podiums(previous_podiums, new_races):
    """Notify every hitchhiker who is on a race podium now but wasn't on the previous one.

    Lives here rather than in show.py (which calls it) because show.py runs its work at
    import time, and rather than in races.py because that module is deliberately pure —
    no app context, no side effects.

    Hitchhikers are matched to accounts by nickname (User.username), the same way
    main.py's _ride_owner_users does it: race entries are keyed on the hitchhiker name
    logged on the ride, and an unregistered name simply has nobody to notify. Matching is
    case-insensitive (hitch/usernames.py) — including "was already on the podium", so a
    standings file written before names were canonicalised doesn't re-notify everyone.
    """
    if previous_podiums is None:
        return
    entered = {}  # username key -> [(race title, position)]
    for race in new_races:
        was_on = {username_key(n) for n in (previous_podiums.get(race.get("name")) or [])}
        for position, entry in enumerate(race.get("entries") or [], start=1):
            name = entry.get("hitchhiker_name")
            if name and username_key(name) not in was_on:
                entered.setdefault(username_key(name), []).append((race.get("title") or race.get("name"), position))
    if not entered:
        return
    for user in db.session.query(User).filter(func.lower(User.username).in_(list(entered))).all():
        for title, position in entered[username_key(user.username)]:
            notify_race_podium(user.id, title, position)


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
    # Every other notification kind links straight to something relevant (a profile, a
    # ride, a thread); this one linked to /leaderboard, which has no connection to who
    # was actually nearby. Link to the first nearby user's profile instead, same pattern
    # notify_new_follower already uses for a single-user link -- for the common one-match
    # case this goes exactly where "See their profiles" promises; for multiple matches
    # it's still a real profile among the group rather than an unrelated page.
    add_notification(
        user_id,
        f"{len(usernames)} {plural} logged near you recently: {names}. See their profiles on the map.",
        link=f"/account/{usernames[0]}",
        kind="nearby",
    )


def unread_count(user):
    """Number of unread notifications for `user` (0 for anonymous/None)."""
    if user is None or user.is_anonymous:
        return 0
    return Notification.query.filter_by(user_id=user.id, is_read=False).count()
