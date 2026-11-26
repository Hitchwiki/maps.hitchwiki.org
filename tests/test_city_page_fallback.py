"""Wiki infobox links to city pages that cities.py never generated must not dead-end."""

import pytest

from hitch.blueprints.utils.city_page_fallback import resolve_missing_city_page


@pytest.fixture
def city_dir(tmp_path):
    for country, cities in {
        "Greece": ["Thessaloníki"],
        "United States": ["Madison", "Richmond"],
        "United Kingdom": ["London"],
        "Iran": ["Qazvīn"],
        "Chile": ["Chillán"],
        "Czechia": ["Brno"],
        "Korea, South": ["Seoul"],
    }.items():
        (tmp_path / country).mkdir()
        for c in cities:
            (tmp_path / country / f"{c}.html").write_text("x")
    return str(tmp_path)


@pytest.mark.parametrize(
    "path,expected",
    [
        ("city/Greece/Thessaloniki.html", (301, "/city/Greece/Thessalon%C3%ADki.html")),
        ("city/Iran/Qazvin.html", (301, "/city/Iran/Qazv%C4%ABn.html")),
        ("city/Chile/chillan.html", (301, "/city/Chile/Chill%C3%A1n.html")),
        ("city/United States of America/Madison.html", (301, "/city/United%20States/Madison.html")),
        ("city/United States of America/Richmond (Virginia).html", (301, "/city/United%20States/Richmond.html")),
        ("city/England, UK/London.html", (301, "/city/United%20Kingdom/London.html")),
        ("city/Czech Republic/Brno.html", (301, "/city/Czechia/Brno.html")),
        ("city/South Korea/Seoul.html", (301, "/city/Korea%2C%20South/Seoul.html")),
        ("city/USA (Oregon)/Madison.html", (301, "/city/United%20States/Madison.html")),
        # No page for the place: the country map, temporarily (a ride may create the page).
        ("city/Greece/Kalamata.html", (302, "/country/Greece")),
        ("city/England, UK/Thurrock Services.html", (302, "/country/United%20Kingdom")),
        ("city/United States of America/Oregon.html", (302, "/country/United%20States")),
        # No country page either: the map's place search at that place.
        ("city/Myanmar/Mandalay.html", (302, "/?ref=wiki-city-search#search/Mandalay%2C%20Myanmar")),
        ("city//Thessaloniki.html", (302, "/?ref=wiki-city-search#search/Thessaloniki")),
        ("city//Swietokrzyskie (Voivodeship).html", (302, "/?ref=wiki-city-search#search/Swietokrzyskie%2C%20Voivodeship")),
        ("city/Germany/Nienburg/Weser.html", (302, "/?ref=wiki-city-search#search/Germany%20Nienburg%20Weser")),
    ],
)
def test_resolves(city_dir, path, expected):
    assert resolve_missing_city_page(city_dir, path) == expected


@pytest.mark.parametrize(
    "path",
    [
        "city/Thessaloniki.html",
        "city/Greece/.html",
        "spots.json",
    ],
)
def test_404s(city_dir, path):
    assert resolve_missing_city_page(city_dir, path) is None


def test_route_redirects_missing_city_page(client, monkeypatch):
    import hitch

    monkeypatch.setattr(hitch, "resolve_missing_city_page", lambda d, p: (302, "/country/Greece"))
    r = client.get("/city/Greece/Kalamata-does-not-exist.html")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/country/Greece")


def test_route_keeps_empty_country_segment(client):
    # The wiki emits /city//<Title>.html for an empty infobox country; the catch-all
    # must still see the empty segment and land on the place search, not a 404.
    r = client.get("/city//Thessaloniki.html")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/?ref=wiki-city-search#search/Thessaloniki")
