"""One rule for deciding whether two hitchhiker names mean the same person.

Rides carry a free-text `nickname`, not a foreign key to `user`, so every "is this ride
mine", "whose profile is this" and "who do I notify" question in the app is a string
comparison. That comparison used to be either exact or MediaWiki-style (`_norm_nickname`:
first letter case-insensitive, the rest exact), which is the rule the wiki itself applies
to account names.

That rule splits people in two. Hitchwiki accounts arrive here through OAuth spelled the
way MediaWiki stores them ("Germanytoindia"), while the same person's imported hitchmap.com
rides carry the name they typed there ("GermanyToIndia"). Differing in an interior letter,
those are two identities: the rides sit on an unregistered stub page their own author
cannot edit, claim credit for, or be followed on. 18 of the 216 registered accounts have
rides logged under a differently-cased spelling of their name.

So: **compare the whole name case-insensitively, and display the spelling of the registered
account whenever one exists.** A person then has one profile, one link and one ride history,
whichever spelling any given ride happens to carry.

Two consequences worth stating, since they are the price of the rule:

* Two Hitchwiki accounts differing only in case (which MediaWiki does allow) would be
  treated as one person here. No such pair exists among registered users, and the merge is
  what the affected people actually want; a `user`-table lookup is still the authority for
  *which* account you are logged in as, so this never lets anyone log in as someone else.
* Case-folding is `str.lower()` and SQL `lower()`, which SQLite applies to ASCII only.
  A name whose case differs in a non-ASCII letter past the first ("Hélia"/"HÉLIA") stays
  two names, exactly as before. Fixing that would mean a custom SQLite collation for a case
  nobody has hit.
"""

from flask import g, has_app_context, has_request_context
from sqlalchemy import func

# Rides with no named hitchhiker carry this sentinel (see publish_ride.ANONYMOUS_NICKNAME),
# and it is a placeholder, not a person: it must never be resolved to an account, however a
# would-be "anonymous" username is spelled.
_ANONYMOUS_KEYS = {"anonymous", ""}


def username_key(name):
    """The identity of a username: case-insensitive over its whole length.

    Use this instead of comparing names with `==`, so every caller splits (or merges)
    identities the same way. Matches SQL `lower(username)`, which is how the same
    comparison is expressed when it has to happen in the database.
    """
    return (name or "").strip().lower()


def same_username(a, b):
    """Whether two hitchhiker names refer to the same person."""
    key = username_key(a)
    return bool(key) and key == username_key(b)


def find_user_ci(username):
    """The registered user whose name matches `username` ignoring case, or None.

    The case-insensitive replacement for `security.datastore.find_user(username=...)`,
    which compares exactly and so hands a "no such user" answer to the very people this
    module exists for.
    """
    from hitch.extensions import db
    from hitch.models import User

    key = username_key(username)
    if not key:
        return None
    return db.session.query(User).filter(func.lower(User.username) == key).first()


def _canonical_names():
    """{lowercased username: username as registered}, cached for the request.

    One 200-row query answers every name on a page (a ride list resolves one name per
    card), and the map of names cannot change mid-request.
    """
    from hitch.extensions import db
    from hitch.models import User

    def build():
        return {username_key(name): name for (name,) in db.session.query(User.username).all() if name}

    # No app context means no database to ask — callers outside one (a pure-function unit
    # test, a standalone script) get names back exactly as logged, which is also what an
    # unregistered name gets anyway. Every request path has a context, so this never
    # weakens the rule where it is actually applied.
    if not has_app_context():
        return {}
    if not has_request_context():
        return build()
    cached = g.get("_canonical_usernames")
    if cached is None:
        cached = build()
        g._canonical_usernames = cached
    return cached


def canonical_username(name):
    """`name` spelled the way its owner's account is, or unchanged if nobody registered it.

    This is what a ride card, a profile link and a leaderboard row should print: the
    nickname on the ride is whatever the author typed on whichever platform the ride came
    from, and showing two spellings of one person implies two people.
    """
    key = username_key(name)
    if key in _ANONYMOUS_KEYS:
        return name
    return _canonical_names().get(key, name)
