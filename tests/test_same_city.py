"""Introducing hitchhikers who are from the same city (hitch/blueprints/utils/same_city.py)."""

import pytest

import hitch.blueprints.utils.same_city as same_city
from hitch.extensions import db as _db
from hitch.models import Notification, User

UQ = "same-city-test-"


def _user(username, city=None, country=None, **kw):
    return User(
        username=username,
        email=kw.pop("email", f"{username.lower()}@example.com"),
        password="x",
        active=True,
        fs_uniquifier=UQ + username,
        origin_city=city,
        origin_country=country,
        **kw,
    )


@pytest.fixture
def people(app):
    with app.app_context():
        yield
        _db.session.rollback()
        ids = [u.id for u in User.query.filter(User.fs_uniquifier.like(UQ + "%"))]
        Notification.query.filter(Notification.user_id.in_(ids)).delete(synchronize_session=False)
        User.query.filter(User.id.in_(ids)).delete(synchronize_session=False)
        _db.session.commit()


def _add(*users):
    _db.session.add_all(users)
    _db.session.commit()
    return users


def _notes(user, kind=None):
    q = Notification.query.filter_by(user_id=user.id)
    return q.filter_by(kind=kind).all() if kind else q.all()


def test_city_match_ignores_case_and_spacing_but_respects_country(people):
    me, twin, other_paris, no_country = _add(
        _user("CityMe", "Paris", "France"),
        _user("CityTwin", " paris ", "France"),
        _user("CityTexas", "Paris", "United States"),
        _user("CityNoCountry", "PARIS"),
    )
    assert {u.username for u in same_city.same_city_users(me)} == {
        "CityTwin",
        "CityNoCountry",
    }


def test_new_arrival_is_announced_once_from_edit_user(app, client, people):
    (old,) = _add(_user("CityLocal", "Hamburg", "Germany"))
    (new,) = _add(_user("CityNewbie"))
    with client.session_transaction() as s:
        s["_user_id"], s["_fresh"] = UQ + "CityNewbie", True

    form = {
        "gender": "",
        "origin_country": "Germany",
        "origin_city": "hamburg",
        "current_country": "",
        "distance_unit": "metric",
        "allow_messages": "y",
    }
    assert client.post("/edit-user", data=form).status_code == 302

    (to_old,) = _notes(old, "same_city")
    assert "CityNewbie" in to_old.message and to_old.link == "/messages/CityNewbie?ref=same_city"
    (to_new,) = _notes(new, "same_city")
    assert "CityLocal" in to_new.message and to_new.link == "/messages/CityLocal?ref=same_city"

    # Saving the profile again is not "joining" again.
    assert client.post("/edit-user", data=form).status_code == 302
    assert len(_notes(old, "same_city")) == 1


def test_one_off_intro_lists_only_chat_reachable_people_and_is_rerunnable(people, monkeypatch):
    emails = []
    monkeypatch.setattr(
        same_city,
        "_send_intro_email",
        lambda u, city, others: emails.append((u.username, city, [o.username for o in others])),
    )
    a, b, quiet, synthetic, loner = _add(
        _user("CityA", "Wrocław", "Poland"),
        _user("CityB", "wrocław", "Poland"),
        _user("CityQuiet", "Wrocław", "Poland", allow_messages=False),
        _user("CitySynth", "Wrocław", "Poland", email="x@hitchwiki.oauth"),
        _user("CityLoner", "Tábor", "Czechia"),
    )

    notified, emailed = same_city.send_same_city_intro()
    assert (notified, emailed) == (
        4,
        3,
    )  # everyone but the loner; no email to the synthetic address
    assert (
        "CityA",
        "Wrocław",
        ["CityB", "CitySynth"],
    ) in emails  # CityQuiet has chat off: never listed
    assert _notes(loner) == []
    assert "CityB" in _notes(a, same_city.INTRO_KIND)[0].message

    assert same_city.send_same_city_intro() == (0, 0)


def test_intro_email_renders_and_is_tagged(app, monkeypatch):
    import hitch.blueprints.utils.send_welcome_email as swe

    captured = {}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {}

    monkeypatch.setattr(
        swe.requests,
        "post",
        lambda url, headers, json, timeout: captured.update(json) or _Resp(),
    )
    with app.app_context():
        same_city._send_intro_email(
            User(username="Chris", email="c@example.com"),
            "Hamburg",
            [User(username="Jaki")],
        )
    assert captured["campaign_id"] == "same-city-intro"
    assert "https://maps.hitchwiki.org/messages/Jaki" in captured["content"]["text"]
    assert "Hamburg" in captured["content"]["html"]


def test_lowercase_city_borrows_a_neighbours_spelling(people):
    me, twin = _add(_user("CityLower", "paris", "France"), _user("CityUpper", "Paris", "France"))
    assert same_city._city_label(me, [twin]) == "Paris"
    assert same_city._city_label(twin, [me]) == "Paris"


def _login(client, username):
    with client.session_transaction() as s:
        s["_user_id"], s["_fresh"] = UQ + username, True


def _profile(origin_city="", origin_country="", current_city="", current_country=""):
    return {
        "gender": "",
        "origin_country": origin_country,
        "origin_city": origin_city,
        "current_country": current_country,
        "current_city": current_city,
        "distance_unit": "metric",
        "allow_messages": "y",
    }


def test_moving_to_a_city_introduces_both_locals_and_other_travellers(client, people):
    local, visitor, elsewhere = _add(
        _user("CityHamburger", "Hamburg", "Germany"),
        _user("CityVisitor", "Lyon", "France", current_city="hamburg", current_country="Germany"),
        _user("CityElsewhere", "Oslo", "Norway"),
    )
    (traveller,) = _add(_user("CityTraveller", "Riga", "Latvia"))
    _login(client, "CityTraveller")

    assert client.post("/edit-user", data=_profile("Riga", "Latvia", "Hamburg", "Germany")).status_code == 302

    for other in (local, visitor):
        (note,) = _notes(other, "same_city")
        assert note.message == "CityTraveller is currently in Hamburg. Say hello in chat!"
        assert note.link == "/messages/CityTraveller?ref=same_city"
    assert _notes(elsewhere) == []
    (mine,) = _notes(traveller, "same_city")
    assert mine.message == "You're in Hamburg! From Hamburg: CityHamburger. Currently in Hamburg: CityVisitor. Say hello in chat!"

    # Re-saving the same place is not a new arrival; moving on to another city is.
    assert client.post("/edit-user", data=_profile("Riga", "Latvia", "Hamburg", "Germany")).status_code == 302
    assert len(_notes(local, "same_city")) == 1
    assert client.post("/edit-user", data=_profile("Riga", "Latvia", "Oslo", "Norway")).status_code == 302
    assert "CityTraveller is currently in Oslo" in _notes(elsewhere, "same_city")[0].message


def test_new_hometown_also_reaches_people_currently_there(client, people):
    (visitor,) = _add(_user("CityPassing", "Lyon", "France", current_city="Wrocław", current_country="Poland"))
    (newbie,) = _add(_user("CityWroclawian"))
    _login(client, "CityWroclawian")

    # Hometown and current city are the same: one introduction, not two.
    assert client.post("/edit-user", data=_profile("Wrocław", "Poland", "Wrocław", "Poland")).status_code == 302
    (note,) = _notes(visitor, "same_city")
    assert note.message == "CityWroclawian from Wrocław just joined Hitchwiki Maps. Say hello in chat!"
    (mine,) = _notes(newbie, "same_city")
    assert mine.message == "Currently in Wrocław: CityPassing. Say hello in chat!"
