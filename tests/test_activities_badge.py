"""The dot on the map's Activities button (main.activities_badge).

It says there is something on /recent worth opening: either the viewer follows nobody
yet, or someone they follow has logged a ride since the last time they looked.
"""

import time

import pytest

from hitch.blueprints.main import BADGE_LOOKBACK_S
from hitch.extensions import db as _db
from hitch.models import Follow, RideEvent, User

_UNIQUIFIER = "activities-badge-test-uniquifier"
DOT = 'id="activities-dot"'


def _ride(d_tag, nickname, created_at):
    """A RideEvent shaped the way the Nostr parser writes them — the badge reads the
    nickname out of `content`, since rides link to users by name, not by foreign key."""
    content = {
        "source": "maps.hitchwiki.org",
        "hitchhikers": [{"nickname": nickname}],
        "stops": [{"location": {"latitude": 51.05, "longitude": 13.73}}],
    }
    return RideEvent(
        id=f"event-{d_tag}",
        kind=36820,
        pubkey="pub",
        sig="sig",
        content=content,
        created_at=created_at,
        d=d_tag,
        submission_time="2026-07-20T10:00:00Z",
        stops=content["stops"],
        hitchhikers=content["hitchhikers"],
        source="maps.hitchwiki.org",
    )


def _user(username, uniquifier=None):
    return User(
        username=username,
        email=f"{username.lower()}@example.com",
        password="x",
        active=True,
        fs_uniquifier=uniquifier or f"uq-{username}",
    )


@pytest.fixture
def people(app):
    """A logged-in-able viewer plus a hitchhiker they can follow."""
    with app.app_context():
        viewer, other = _user("badgeviewer", _UNIQUIFIER), _user("GermanyToIndia")
        _db.session.add_all([viewer, other])
        _db.session.commit()
        ids = (viewer.id, other.id)
    yield ids
    with app.app_context():
        RideEvent.query.delete()
        Follow.query.delete()
        for user_id in ids:
            user = _db.session.get(User, user_id)
            if user:
                _db.session.delete(user)
        _db.session.commit()


@pytest.fixture
def login(client):
    with client.session_transaction() as sess:
        sess["_user_id"] = _UNIQUIFIER
        sess["_fresh"] = True


def _follow(app, follower_id, followed_id):
    with app.app_context():
        _db.session.add(Follow(follower_id=follower_id, followed_id=followed_id))
        _db.session.commit()


def _add_ride(app, nickname, age_s=60):
    with app.app_context():
        _db.session.add(_ride(f"d-{nickname}-{age_s}", nickname, int(time.time()) - age_s))
        _db.session.commit()


def _seen(app, viewer_id, ago_s=0):
    """Mark the viewer as having opened /recent `ago_s` seconds ago."""
    with app.app_context():
        _db.session.get(User, viewer_id).recent_seen_at = int(time.time()) - ago_s
        _db.session.commit()


def _has_dot(client):
    return DOT in client.get("/").get_data(as_text=True)


def test_anonymous_visitors_never_get_a_dot(client, people):
    # They can't follow anyone and can't clear it, so it would be permanent noise.
    assert not _has_dot(client)


def test_following_nobody_shows_the_dot(client, people, login):
    # /recent answers exactly this case with its follow suggestions.
    assert _has_dot(client)


def test_a_followed_hitchhikers_new_ride_shows_the_dot(client, app, people, login):
    viewer_id, other_id = people
    _follow(app, viewer_id, other_id)
    _seen(app, viewer_id, ago_s=300)
    assert not _has_dot(client)

    _add_ride(app, "GermanyToIndia")
    assert _has_dot(client)


def test_a_ride_the_viewer_has_already_seen_does_not(client, app, people, login):
    viewer_id, other_id = people
    _follow(app, viewer_id, other_id)
    _add_ride(app, "GermanyToIndia")
    _seen(app, viewer_id)
    assert not _has_dot(client)


def test_a_ride_by_someone_they_do_not_follow_does_not(client, app, people, login):
    viewer_id, other_id = people
    _follow(app, viewer_id, other_id)
    _seen(app, viewer_id, ago_s=300)
    _add_ride(app, "stranger")
    assert not _has_dot(client)


def test_the_nickname_match_is_case_insensitive(client, app, people, login):
    # A Hitchwiki account arrives spelled one way and the same person's imported rides
    # another; they are one hitchhiker (hitch/usernames.py).
    viewer_id, other_id = people
    _follow(app, viewer_id, other_id)
    _seen(app, viewer_id, ago_s=300)
    _add_ride(app, "germanytoindia")
    assert _has_dot(client)


def test_nothing_older_than_the_lookback_lights_it(client, app, people, login):
    # A viewer who has never opened /recent (recent_seen_at NULL) would otherwise ask
    # about every ride a followed user ever logged, on the app's most-requested page.
    viewer_id, other_id = people
    _follow(app, viewer_id, other_id)
    _add_ride(app, "GermanyToIndia", age_s=BADGE_LOOKBACK_S + 3600)
    assert not _has_dot(client)


def test_opening_the_activities_page_clears_it(client, app, people, login):
    viewer_id, other_id = people
    _follow(app, viewer_id, other_id)
    _add_ride(app, "GermanyToIndia")
    assert _has_dot(client)

    assert client.get("/recent").status_code == 200
    with app.app_context():
        assert _db.session.get(User, viewer_id).recent_seen_at is not None
    assert not _has_dot(client)
