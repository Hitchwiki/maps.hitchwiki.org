import pytest

from hitch.models import Follow, Notification, RideLike, Trip, TripRide, User


@pytest.fixture(autouse=True)
def _cleanup(app, db):
    yield
    db.session.rollback()
    for model in (Follow, Notification, TripRide, Trip, RideLike):
        db.session.query(model).delete()
    db.session.query(User).filter(
        (User.email.like("%@example.org")) | (User.email.like("deleted-%@deleted.invalid"))
    ).delete(synchronize_session=False)
    db.session.commit()


def _user(db, name, email):
    u = User(username=name, email=email, password="x", fs_uniquifier=f"uq-{name}", active=True)
    u.origin_city = "Berlin"
    u.hitchwiki_username = name
    db.session.add(u)
    db.session.commit()
    return u


def _login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = user.fs_uniquifier
        sess["_fresh"] = True


def test_wrong_confirmation_deletes_nothing(app, db, client):
    u = _user(db, "erase_a", "a@example.org")
    _login(client, u)
    r = client.post("/delete-account", data={"confirm_username": "someone else"})
    assert r.status_code == 303 and "error=confirm" in r.headers["Location"]
    db.session.refresh(u)
    assert u.active and u.email == "a@example.org"


def test_anonymous_post_is_redirected(app, db, client):
    r = client.post("/delete-account", data={"confirm_username": "x"})
    assert r.status_code == 303


def test_erase_scrubs_account_and_keeps_other_users(app, db, client):
    a = _user(db, "erase_b", "b@example.org")
    other = _user(db, "erase_other", "o@example.org")
    db.session.add_all(
        [
            Follow(follower_id=a.id, followed_id=other.id),
            Follow(follower_id=other.id, followed_id=a.id),
            Notification(user_id=a.id, message="hi"),
            Notification(user_id=other.id, message="keep"),
            RideLike(ride_d_tag="d1", user_id=a.id),
        ]
    )
    trip = Trip(user_id=a.id, name="Balkans")
    db.session.add(trip)
    db.session.flush()
    db.session.add(TripRide(trip_id=trip.id, ride_d_tag="d1"))
    db.session.commit()
    aid = a.id

    _login(client, a)
    r = client.post("/delete-account", data={"confirm_username": "ERASE_B"})
    assert r.status_code == 303 and "done=1" in r.headers["Location"]

    db.session.expire_all()
    gone = db.session.get(User, aid)
    assert gone.username is None and gone.email == f"deleted-{aid}@deleted.invalid"
    assert gone.active is False and gone.origin_city is None and gone.hitchwiki_username is None
    assert db.session.query(Follow).filter((Follow.follower_id == aid) | (Follow.followed_id == aid)).count() == 0
    assert db.session.query(Notification).filter_by(user_id=aid).count() == 0
    assert db.session.query(Trip).filter_by(user_id=aid).count() == 0
    assert db.session.query(TripRide).filter_by(ride_d_tag="d1").count() == 0
    assert db.session.query(RideLike).filter_by(user_id=aid).count() == 0
    assert db.session.query(Notification).filter_by(user_id=other.id).count() == 1
    assert db.session.get(User, other.id).email == "o@example.org"

    # the old session no longer works
    assert client.get("/me.json").status_code in (401, 302, 200)
