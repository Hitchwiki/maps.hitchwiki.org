"""Which place the map's Hitchhikers mode shows a user at (hitch/blueprints/utils/hitchhiker_places.py)."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from hitch.blueprints.utils.hitchhiker_places import cache_key, chosen_place, geocode, geocode_all, hitchhiker_entries

NOW = datetime(2026, 10, 6, 12, 0)


def _user(id=1, username="Anna", **kw):
    fields = dict(
        origin_city=None,
        origin_country=None,
        current_city=None,
        current_country=None,
        current_location_updated_at=None,
        allow_messages=True,
    )
    fields.update(kw)
    return SimpleNamespace(id=id, username=username, **fields)


def test_recent_current_city_wins_over_hometown():
    u = _user(
        origin_city="Hamburg",
        current_city="Tbilisi",
        current_country="Georgia",
        current_location_updated_at=NOW - timedelta(days=3),
    )
    assert chosen_place(u, NOW)[:3] == ("Tbilisi", "Georgia", "current")


def test_stale_current_city_falls_back_to_hometown():
    # Someone who said "Tbilisi" four months ago is not in Tbilisi any more.
    u = _user(
        origin_city="Hamburg",
        origin_country="Germany",
        current_city="Tbilisi",
        current_location_updated_at=NOW - timedelta(days=120),
    )
    assert chosen_place(u, NOW)[:3] == ("Hamburg", "Germany", "home")


def test_country_alone_is_not_a_place():
    u = _user(current_country="Georgia", current_location_updated_at=NOW)
    assert chosen_place(u, NOW) is None


def test_whitespace_is_collapsed():
    assert chosen_place(_user(origin_city="  Linz  "), NOW)[0] == "Linz"


def test_geocode_falls_back_to_city_then_first_segment_and_caches_misses():
    asked = []

    def fetch(q, lang="en"):
        asked.append(q)
        return {"lat": 1, "lon": 2, "name": "Häädemeeste"} if q == "Häädemeeste" else None

    cache = {}
    assert geocode("Häädemeeste/Tartu", "Estonia", cache, fetch=fetch, sleep=lambda s: None) == {"lat": 1, "lon": 2}
    assert asked == ["Häädemeeste/Tartu, Estonia", "Häädemeeste/Tartu", "Häädemeeste"]
    # A place Photon has no answer for is remembered as null, never retried.
    geocode("Nowhereville", "", cache, fetch=lambda q, lang="en": None, sleep=lambda s: None)
    assert cache[cache_key("Nowhereville", "")] is None
    geocode("nowhereville ", "", cache, fetch=lambda q, lang="en": pytest.fail("cached"), sleep=lambda s: None)


def test_lookalike_results_are_rejected():
    results = {
        "Tbilisi, Germany": {"lat": 49, "lon": 7, "name": "Tifliser Platz"},
        "Tbilisi": {"lat": 41.7, "lon": 44.8, "name": "Tbilisi"},
    }
    assert geocode("Tbilisi", "Germany", {}, fetch=lambda q, lang="en": results.get(q), sleep=lambda s: None) == {
        "lat": 41.7,
        "lon": 44.8,
    }


def test_exonym_is_accepted_by_its_local_name():
    names = {"en": "Prague", "default": "Praha"}
    hit = geocode(
        "Praha", "Czechia", {}, fetch=lambda q, lang="en": {"lat": 50.1, "lon": 14.4, "name": names[lang]}, sleep=lambda s: None
    )
    assert hit == {"lat": 50.1, "lon": 14.4}


@pytest.mark.parametrize(
    "typed,found", [("Kiiv", "Kyiv"), ("Århus", "Aarhus"), ("Tel-Aviv", "Tel Aviv"), ("Ebersbach Sachsen", "Ebersbach")]
)
def test_exonyms_and_accents_still_match(typed, found):
    from hitch.blueprints.utils.hitchhiker_places import resembles

    assert resembles(typed, found)


def test_failed_request_caches_nothing():
    def boom(q):
        raise OSError("photon down")

    cache = {}
    geocode_all([("Lyon", "France")], cache, fetch=boom, sleep=lambda s: None)
    assert cache == {}


def test_entries_carry_only_what_the_profile_shows():
    cache = {cache_key("Tbilisi", "Georgia"): {"lat": 41.7, "lon": 44.8}, cache_key("Lyon", "France"): None}
    users = [
        _user(
            1,
            "Anna",
            origin_city="Hamburg",
            current_city="Tbilisi",
            current_country="Georgia",
            current_location_updated_at=NOW - timedelta(days=1),
        ),
        _user(2, "Ben", origin_city="Lyon", origin_country="France"),  # not geocodable → left off
        _user(3, "Cleo", allow_messages=False),  # no place at all
    ]
    entries = hitchhiker_entries(users, cache, avatars={1: "/profile-images/a.jpg"}, now=NOW)
    assert entries == [
        {
            "u": "Anna",
            "lat": 41.7,
            "lon": 44.8,
            "place": "Tbilisi, Georgia",
            "k": "current",
            "since": (NOW - timedelta(days=1)).strftime("%Y-%m-%d"),
            "from": "Hamburg",
            "msg": True,
            "img": "/profile-images/a.jpg",
        }
    ]


def test_no_chat_link_for_people_who_turned_messages_off():
    cache = {cache_key("Lyon", "France"): {"lat": 45.7, "lon": 4.8}}
    [entry] = hitchhiker_entries([_user(origin_city="Lyon", origin_country="France", allow_messages=False)], cache, now=NOW)
    assert "msg" not in entry
