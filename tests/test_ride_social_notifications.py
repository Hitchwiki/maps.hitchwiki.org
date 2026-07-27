"""Notifications for the social features: likes, comments, and race podiums.

The rules under test are the product ones, not the plumbing: every comment notifies the
ride's owner, but only the *first* like on a ride does (later likers would evict the
owner's other notifications from the 10-row window one at a time), and a hitchhiker is
told when they enter a race's top 3 — once, on entering.
"""

import time

import pytest

from hitch.blueprints.utils.notifications import load_race_podiums, notify_new_race_podiums, notify_race_podium
from hitch.extensions import db as _db
from hitch.models import Follow, Notification, RideEvent, RideLike, User

_OWNER_UNIQUIFIER = "ride-social-owner-uniquifier"


def _make_user(username, uniquifier):
    return User(
        username=username,
        email=f"{username}@example.com",
        password="x",
        active=True,
        fs_uniquifier=uniquifier,
    )


def _make_ride(d_tag, nickname):
    stops = [{"location": {"latitude": 51.0, "longitude": 13.0}}]
    content = {"source": "maps.hitchwiki.org", "hitchhikers": [{"nickname": nickname}], "stops": stops}
    return RideEvent(
        id=f"event-{d_tag}",
        kind=36820,
        pubkey="pub",
        sig="sig",
        content=content,
        created_at=int(time.time()),
        d=d_tag,
        submission_time="2026-07-20T10:00:00Z",
        stops=stops,
        hitchhikers=content["hitchhikers"],
        source="maps.hitchwiki.org",
    )


@pytest.fixture
def world(app):
    """A ride owned by `rideowner`, plus two other users the owner follows.

    The follow matters for comments: commenting on someone else's ride requires that they
    already follow you (see _user_can_comment_on_ride).
    """
    with app.app_context():
        owner = _make_user("rideowner", _OWNER_UNIQUIFIER)
        liker = _make_user("firstliker", "ride-social-liker-uniquifier")
        other = _make_user("secondliker", "ride-social-other-uniquifier")
        _db.session.add_all([owner, liker, other])
        _db.session.commit()
        _db.session.add_all(
            [
                _make_ride("social-ride-1", "rideowner"),
                Follow(follower_id=owner.id, followed_id=liker.id),
                Follow(follower_id=owner.id, followed_id=other.id),
            ]
        )
        _db.session.commit()
        ids = {"owner": owner.id, "liker": liker.id, "other": other.id}

    yield ids

    with app.app_context():
        Notification.query.delete()
        RideLike.query.delete()
        Follow.query.delete()
        RideEvent.query.filter_by(d="social-ride-1").delete()
        for uid in ids.values():
            user = _db.session.get(User, uid)
            if user:
                _db.session.delete(user)
        _db.session.commit()


def _login(client, uniquifier):
    with client.session_transaction() as sess:
        sess["_user_id"] = uniquifier
        sess["_fresh"] = True


def _owner_notifications(app, owner_id, kind):
    with app.app_context():
        return Notification.query.filter_by(user_id=owner_id, kind=kind).all()


def test_first_like_notifies_the_owner(app, client, world):
    _login(client, "ride-social-liker-uniquifier")
    client.post("/like-ride/social-ride-1")

    notes = _owner_notifications(app, world["owner"], "ride_like")
    assert len(notes) == 1
    assert "firstliker" in notes[0].message
    # The link must lead back to the ride that was liked.
    assert notes[0].link == "/ride/social-ride-1"


def test_second_like_does_not_notify_again(app, client, world):
    _login(client, "ride-social-liker-uniquifier")
    client.post("/like-ride/social-ride-1")
    _login(client, "ride-social-other-uniquifier")
    client.post("/like-ride/social-ride-1")

    assert len(_owner_notifications(app, world["owner"], "ride_like")) == 1


def test_unlike_then_relike_does_not_notify_again(app, client, world):
    """The like count returns to zero on an unlike, so the "first like" test alone would
    fire a second time — notify_ride_like's per-ride dedupe is what prevents it."""
    _login(client, "ride-social-liker-uniquifier")
    client.post("/like-ride/social-ride-1")  # like
    client.post("/like-ride/social-ride-1")  # unlike
    client.post("/like-ride/social-ride-1")  # like again

    assert len(_owner_notifications(app, world["owner"], "ride_like")) == 1


def test_liking_your_own_ride_notifies_nobody(app, client, world):
    _login(client, _OWNER_UNIQUIFIER)
    client.post("/like-ride/social-ride-1")

    assert _owner_notifications(app, world["owner"], "ride_like") == []


def test_every_comment_notifies_the_owner(app, client, world):
    """Unlike likes, comments each carry content the owner may want to answer, so all of
    them notify — including a second commenter's."""
    _login(client, "ride-social-liker-uniquifier")
    client.post("/comment-ride/social-ride-1", data={"body": "nice spot"})
    client.post("/comment-ride/social-ride-1", data={"body": "was it busy?"})
    _login(client, "ride-social-other-uniquifier")
    client.post("/comment-ride/social-ride-1", data={"body": "hitched there too"})

    notes = _owner_notifications(app, world["owner"], "ride_comment")
    assert len(notes) == 3
    # Every one points at the comment section of the ride it was made on.
    assert {n.link for n in notes} == {"/ride/social-ride-1#comments"}


def test_race_podium_notifies_only_new_entrants(app, world):
    previous = {"berlin-prague": ["rideowner", "someoneelse"]}
    new_races = [
        {
            "name": "berlin-prague",
            "title": "Berlin → Prague",
            # rideowner was already on this podium (moving 1st -> 2nd is not "entering"),
            # firstliker is new.
            "entries": [{"hitchhiker_name": "firstliker"}, {"hitchhiker_name": "rideowner"}],
        }
    ]
    with app.app_context():
        notify_new_race_podiums(previous, new_races)

        assert Notification.query.filter_by(user_id=world["owner"], kind="race_podium").all() == []
        notes = Notification.query.filter_by(user_id=world["liker"], kind="race_podium").all()
        assert len(notes) == 1
        assert "Berlin → Prague" in notes[0].message
        assert "#1" in notes[0].message
        assert notes[0].link == "/races"


def test_race_podium_notification_is_once_per_race(app, world):
    """Dropping off the podium and climbing back on must not notify twice — the message
    text differs (the position changed), so the dedupe has to key on the race."""
    with app.app_context():
        notify_race_podium(world["liker"], "Berlin → Prague", 3)
        notify_race_podium(world["liker"], "Berlin → Prague", 2)
        notify_race_podium(world["liker"], "Lisbon → Porto", 1)

        notes = Notification.query.filter_by(user_id=world["liker"], kind="race_podium").all()
        assert len(notes) == 2
        assert "#3" in " ".join(n.message for n in notes)


def test_no_previous_races_file_notifies_nobody(app, world, tmp_path):
    """A first-ever build has nothing to diff against; notifying then would announce
    podiums that have stood for weeks."""
    assert load_race_podiums(str(tmp_path / "nope.json")) is None
    with app.app_context():
        notify_new_race_podiums(None, [{"name": "r", "title": "R", "entries": [{"hitchhiker_name": "firstliker"}]}])
        assert Notification.query.filter_by(kind="race_podium").all() == []
