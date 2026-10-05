"""Introduce hitchhikers who are from, or currently in, the same city.

`origin_city` is free text the user types on /edit-user ("Hamburg", "hamburg ",
"Paris"), so "the same city" is decided by `city_key`: case-folded, whitespace-collapsed
city, plus the country when *both* people picked one — Paris, France and Paris, Texas
must not be introduced to each other, but someone who left the country blank still
matches on the city alone.

Each user can name two places — where they are from (`origin_*`) and where they are
right now (`current_*`) — and the live introductions match either against either: a
traveller passing through Hamburg wants to meet the people from Hamburg *and* the other
travellers there this week.

Entry points:
- `introduce_after_profile_save` — called from /edit-user after every save. It fires when
  a user saves a hometown for the first time (accounts are created by OAuth with no
  city, so this is when a hitchhiker "joins" a city), and when their "currently in" city
  changes to a new one. Both sides are told. Re-saving an unchanged place never re-fires.
- `send_same_city_intro` — the one-off hometown backfill (hitch/scripts/same_city_intro.py)
  for people who were already from the same city before this existed. Already run on
  2026-10-05; hometown-only, as it was sent.

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


def _key(city, country):
    city = _norm(city)
    return (city, _norm(country)) if city else None


def city_key(user):
    """Hometown (city, country) match key for `user`, or None when they gave no city."""
    return _key(user.origin_city, user.origin_country)


def current_key(user):
    """ "Currently in" match key, or None — a country alone is too coarse to introduce on."""
    return _key(getattr(user, "current_city", None), getattr(user, "current_country", None))


def same_place(a, b):
    return a is not None and b is not None and a[0] == b[0] and (not a[1] or not b[1] or a[1] == b[1])


def same_city_users(user, candidates=None):
    """Other active users from `user`'s city, oldest account first."""
    key = city_key(user)
    if key is None:
        return []
    if candidates is None:
        candidates = User.query.filter(User.origin_city.isnot(None), User.active.is_(True)).order_by(User.id).all()
    return [u for u in candidates if u.id != user.id and u.active and same_place(key, city_key(u))]


def _city_label(user, neighbours=(), current=False):
    """The city as the user typed it — unless they typed it all lowercase ("paris"), then
    a neighbour's capitalised spelling of the same city, so the text doesn't read odd."""
    raw = user.current_city if current else user.origin_city
    key = _key(raw, None)
    label = " ".join(raw.split())
    if label.islower():
        spellings = [n.origin_city for n in neighbours] + [getattr(n, "current_city", None) for n in neighbours]
        label = next((" ".join(c.split()) for c in spellings if c and _key(c, None) == key and not c.islower()), label)
    return label


def people_from_or_in(key, exclude_id):
    """Active users from `key`'s city and users currently in it, as two disjoint lists
    (someone both from and currently in the city counts as "from"), oldest account first."""
    candidates = (
        User.query.filter((User.origin_city.isnot(None)) | (User.current_city.isnot(None)), User.active.is_(True))
        .order_by(User.id)
        .all()
    )
    from_here, here_now = [], []
    for u in candidates:
        if u.id == exclude_id:
            continue
        if same_place(key, city_key(u)):
            from_here.append(u)
        elif same_place(key, current_key(u)):
            here_now.append(u)
    return from_here, here_now


def _names(users):
    names = ", ".join(u.username for u in users[:MAX_LISTED])
    return names + (f" and {len(users) - MAX_LISTED} more" if len(users) > MAX_LISTED else "")


def _who_is_there(from_here, here_now, city):
    parts = []
    if from_here:
        parts.append(f"From {city}: {_names(from_here)}.")
    if here_now:
        parts.append(f"Currently in {city}: {_names(here_now)}.")
    return " ".join(parts) + " Say hello in chat!"


def _chat_link(username):
    return f"/messages/{username}?ref=same_city"


def _list_message(users, city):
    names = [u.username for u in users[:MAX_LISTED]]
    who = ", ".join(names) + (f" and {len(users) - MAX_LISTED} more" if len(users) > MAX_LISTED else "")
    if len(users) == 1:
        return f"{who} is from {city} too. Say hello in chat!"
    return f"{len(users)} hitchhikers are from {city} too: {who}. Say hello in chat!"


def _introduce(user, key, current):
    from_here, here_now = people_from_or_in(key, user.id)
    neighbours = from_here + here_now
    if not neighbours:
        return
    city = _city_label(user, neighbours, current=current)
    if user.allow_messages:
        announcement = (
            f"{user.username} is currently in {city}. Say hello in chat!"
            if current
            else f"{user.username} from {city} just joined Hitchwiki Maps. Say hello in chat!"
        )
        for other in neighbours:
            add_notification(other.id, announcement, link=_chat_link(user.username), kind="same_city")
    from_here = [u for u in from_here if u.allow_messages]
    here_now = [u for u in here_now if u.allow_messages]
    if from_here or here_now:
        first = (from_here + here_now)[0]
        message = (f"You're in {city}! " if current else "") + _who_is_there(from_here, here_now, city)
        add_notification(user.id, message, link=_chat_link(first.username), kind="same_city")


def introduce_after_profile_save(user, had_home, old_current):
    """Introduce `user` after a profile save, given their hometown/current place *before*
    it. Never raises: a notification must never turn a profile save into a 500."""
    try:
        home, current = city_key(user), current_key(user)
        home_joined = not had_home and home is not None
        moved = current is not None and not same_place(old_current, current)
        if home_joined:
            _introduce(user, home, current=False)
        # Setting hometown and "currently in" to the same city in one save would tell the
        # same people twice; the hometown introduction already covers it.
        if moved and not (home_joined and same_place(home, current)):
            _introduce(user, current, current=True)
    except Exception:
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
        city = _city_label(user, reachable)
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
