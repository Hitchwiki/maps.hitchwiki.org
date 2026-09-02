"""cities.py renders city_template.html with a bare (non-Flask-`render_template`)
Jinja Environment, exactly mirrored here. Regression coverage for the nav link to
/route/index.html: without it, the ~400 SEO route pages (route_pages.py) are only
reachable via sitemap.xml -- indexed, but with no path a browsing human or an
internal-link crawl signal ever takes. See route_template.html's own nav, which
already links back to city pages the same way.
"""

import pandas as pd
from flask import g
from jinja2 import Environment, FileSystemLoader

from hitch.translations import SUPPORTED_LANGUAGES, t
from hitch.translations.weekdays import with_weekday


class _FakeCity:
    city = "Berlin"
    country = "Germany"
    lat = 52.52
    lng = 13.405


def _render(app, lang, nearby=None, first_hitch=None):
    with app.app_context():
        g.lang = lang
        env = Environment(loader=FileSystemLoader("hitch/templates"))
        env.globals["t"] = t
        env.globals["g"] = g
        env.globals["SUPPORTED_LANGUAGES"] = SUPPORTED_LANGUAGES
        env.globals["with_weekday"] = with_weekday
        template = env.get_template("city_template.html")
        return template.render(
            city=_FakeCity(),
            title="Berlin",
            reviews=pd.DataFrame(columns=["text", "user_link", "date"]),
            canonical_url=f"https://maps.hitchwiki.org/{'' if lang == 'en' else lang + '/'}city/Germany/Berlin.html",
            alternate_urls=[],
            nearby=nearby or [],
            city_jsonld={},
            first_hitch=first_hitch,
        )


def test_city_page_links_to_the_route_index(app):
    out = _render(app, "en")
    assert 'href="/route/index.html"' in out
    assert "Hitchhiking routes between cities" in out


def test_city_page_route_link_survives_translation(app):
    """The link's href is the same fixed English URL in every language (route_pages.py
    only ever generates one, English-only route tree -- see its own g.lang = "en")."""
    out = _render(app, "de")
    assert 'href="/route/index.html"' in out


def test_nearby_city_links_render_when_supplied(app):
    """cities.py hands the template a list of (label, url) for the nearest other
    city guides; each becomes an inbound internal link the isolated page lacked."""
    nearby = [
        ("Potsdam, Germany", "https://maps.hitchwiki.org/city/Germany/Potsdam.html"),
        ("Leipzig, Germany", "https://maps.hitchwiki.org/city/Germany/Leipzig.html"),
    ]
    out = _render(app, "en", nearby=nearby)
    assert 'id="nearby-cities"' in out
    assert 'href="https://maps.hitchwiki.org/city/Germany/Potsdam.html"' in out
    assert "Leipzig, Germany" in out


def test_nearby_block_absent_when_empty(app):
    out = _render(app, "en", nearby=[])
    assert 'id="nearby-cities"' not in out


def test_first_hitch_block_absent_by_default(app):
    """cities.py passes first_hitch=None for any city with no cell clearing the bar."""
    out = _render(app, "en")
    assert 'class="first-hitch"' not in out
    assert "first-hitch-spot" not in out


def test_first_hitch_block_renders_computed_line(app):
    """When cities.py finds a best-evidenced starting cell it hands the template a
    dict of pure computed numbers; the line and the map link to that cell appear."""
    fh = {
        "lat": 52.44,
        "lon": 13.33,
        "n": 14,
        "mean_rating": 4.6,
        "median_wait": 15,
        "km_from_centre": 9.1,
        "direction": "south-west",
    }
    out = _render(app, "en", first_hitch=fh)
    assert 'class="first-hitch"' in out
    assert 'href="/#location,52.44,13.33,14"' in out
    assert "9.1 km south-west" in out
    assert "14 logged rides" in out
    assert "4.6 out of 5" in out
    assert "city_first_hitch_shown" in out
