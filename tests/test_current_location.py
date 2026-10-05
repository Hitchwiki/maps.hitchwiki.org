"""'Currently in City, Country' on the profile, with the date it was last changed."""

import pytest

from hitch.extensions import db as _db
from hitch.models import User

UQ = "current-location-test-uniquifier"


@pytest.fixture
def me(app, client):
    with app.app_context():
        user = User(username="nowhitcher", email="n@example.com", password="x", active=True, fs_uniquifier=UQ)
        _db.session.add(user)
        _db.session.commit()
        uid = user.id
    with client.session_transaction() as s:
        s["_user_id"], s["_fresh"] = UQ, True
    yield uid
    with client.session_transaction() as s:
        s.clear()
    with app.app_context():
        _db.session.delete(_db.session.get(User, uid))
        _db.session.commit()


def _form(city="", country=""):
    return {"gender": "", "origin_country": "", "distance_unit": "metric", "current_city": city, "current_country": country}


def _user(app, uid):
    with app.app_context():
        return _db.session.get(User, uid)


def test_current_location_is_saved_dated_and_shown(app, client, me):
    assert client.post("/edit-user", data=_form(" Tbilisi ", "Georgia")).status_code == 302
    user = _user(app, me)
    assert (user.current_city, user.current_country) == ("Tbilisi", "Georgia")
    stamp = user.current_location_updated_at
    assert stamp is not None

    page = client.get("/account/nowhitcher").data.decode()
    assert "Currently in Tbilisi, Georgia" in page
    assert f"updated {stamp:%Y-%m-%d}" in page

    # Re-saving the same place must not refresh the date: it says when they *moved*.
    assert client.post("/edit-user", data=_form("Tbilisi", "Georgia")).status_code == 302
    assert _user(app, me).current_location_updated_at == stamp

    # Clearing both removes the line and the date.
    assert client.post("/edit-user", data=_form()).status_code == 302
    user = _user(app, me)
    assert user.current_city is None and user.current_location_updated_at is None
    assert "Currently in" not in client.get("/account/nowhitcher").data.decode()


def test_country_alone_is_enough(app, client, me):
    assert client.post("/edit-user", data=_form(country="Iran, Islamic Republic of")).status_code == 302
    assert "Currently in Iran, Islamic Republic of" in client.get("/account/nowhitcher").data.decode()
