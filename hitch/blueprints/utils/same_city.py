"""Introduce hitchhikers who are from the same city.

`origin_city` is free text the user types on /edit-user ("Hamburg", "hamburg ",
"Paris"), so "the same city" is decided by `city_key`: case-folded, whitespace-collapsed
city, plus the country when *both* people picked one — Paris, France and Paris, Texas
must not be introduced to each other, but someone who left the country blank still
matches on the city alone.

Two entry points:
- `introduce_new_arrival` — called from /edit-user the first time a user saves a city
  (accounts are created by OAuth with no city, so this is the moment a hitchhiker
  "joins" a city). Everyone already there is told, and the newcomer is told who is there.
- `send_same_city_intro` — the one-off backfill (hitch/scripts/same_city_intro.py) for
  people who were already in the same city before this existed.

Only people who accept messages are ever *listed*: the whole point is "say hello in
chat", and listing someone with chat turned off invites a hello they can't receive.
In-app only for the live path (a notification per arrival); email only for the one-off,
which has to reach people who no longer open the site.
"""

import logging

from flask import render_template

from hitch.blueprints.utils.notifications import add_notification
from hitch.blueprints.utils.send_welcome_email import _SYNTHETIC_EMAIL_SUFFIX, _send_via_sparkpost
from hitch.models import User

logger = logging.getLogger(__name__)

# Upper bound on names in one notification; the largest city group in prod is 5.
MAX_LISTED = 10
INTRO_KIND = "same_city_intro"
EMAIL_SUBJECT = "Hitchhikers from your city are on Hitchwiki Maps"


def _norm(text):
    return " ".join((text or "").split()).casefold()


def city_key(user):
    """(city, country) match key for `user`, or None when they gave no city."""
    city = _norm(user.origin_city)
    return (city, _norm(user.origin_country)) if city else None


def _same_place(a, b):
    return a[0] == b[0] and (not a[1] or not b[1] or a[1] == b[1])


def same_city_users(user, candidates=None):
    """Other active users from `user`'s city, oldest account first."""
    key = city_key(user)
    if key is None:
        return []
    if candidates is None:
        candidates = User.query.filter(User.origin_city.isnot(None), User.active.is_(True)).order_by(User.id).all()
    return [u for u in candidates if u.id != user.id and u.active and (k := city_key(u)) and _same_place(key, k)]


def _city_label(user):
    return " ".join(user.origin_city.split())


def _chat_link(username):
    return f"/messages/{username}"


def _list_message(users, city):
    names = [u.username for u in users[:MAX_LISTED]]
    who = ", ".join(names) + (f" and {len(users) - MAX_LISTED} more" if len(users) > MAX_LISTED else "")
    if len(users) == 1:
        return f"{who} is from {city} too. Say hello in chat!"
    return f"{len(users)} hitchhikers are from {city} too: {who}. Say hello in chat!"


def introduce_new_arrival(user):
    """`user` just set their city for the first time: tell both sides. Never raises."""
    try:
        neighbours = same_city_users(user)
        if not neighbours:
            return
        city = _city_label(user)
        if user.allow_messages:
            for other in neighbours:
                add_notification(
                    other.id,
                    f"{user.username} from {city} just joined Hitchwiki Maps. Say hello in chat!",
                    link=_chat_link(user.username),
                    kind="same_city",
                )
        reachable = [u for u in neighbours if u.allow_messages]
        if reachable:
            add_notification(user.id, _list_message(reachable, city), link=_chat_link(reachable[0].username), kind="same_city")
    except Exception:
        # A notification must never turn a profile save into a 500.
        logger.exception("same-city introduction failed for %s", user.username)


def _send_intro_email(user, city, others):
    name = user.username or "there"
    ctx = {"name": name, "city": city, "others": [u.username for u in others[:MAX_LISTED]]}
    html = render_template("email/same_city.html", **ctx)
    text = render_template("email/same_city.txt", **ctx)
    return _send_via_sparkpost(user.email, name, EMAIL_SUBJECT, html, text, transactional=False, campaign="same-city-intro")


def send_same_city_intro(dry_run=False):
    """One-off: tell every user with a same-city neighbour who that is. Returns
    (notified, emailed). Re-runnable: a user who already has the intro notification is
    skipped, so an interrupted run can simply be started again."""
    from hitch.models import Notification

    users = User.query.filter(User.origin_city.isnot(None), User.active.is_(True)).order_by(User.id).all()
    notified = emailed = 0
    for user in users:
        reachable = [u for u in same_city_users(user, users) if u.allow_messages]
        if not reachable:
            continue
        if Notification.query.filter_by(user_id=user.id, kind=INTRO_KIND).first() is not None:
            continue
        city = _city_label(user)
        logger.info("%s (%s): %s", user.username, city, ", ".join(u.username for u in reachable))
        if dry_run:
            notified += 1
            continue
        if user.email_notifications and user.email and not user.email.endswith(_SYNTHETIC_EMAIL_SUFFIX):
            try:
                _send_intro_email(user, city, reachable)
                emailed += 1
            except Exception:
                logger.exception("same-city intro email to %s failed", user.username)
        add_notification(user.id, _list_message(reachable, city), link=_chat_link(reachable[0].username), kind=INTRO_KIND)
        notified += 1
    return notified, emailed
