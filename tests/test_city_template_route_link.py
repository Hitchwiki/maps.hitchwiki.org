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


def _render(app, lang):
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
            city_jsonld={},
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
