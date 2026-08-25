"""Both /route/index.html (route_pages.py's ~400 SEO route pages) and
/why-not-hitchhike (why_not_hitchhike.py) are generated pages that used to have
no link anywhere in the main app menu -- reachable only by someone who already
knew the exact URL, and (for /route/index.html) via the sitemap. Regression
coverage that the main menu keeps linking to both, matching test_play_store_links.py's
plain source-text-assertion style since map.html has no per-render test harness.
"""

from pathlib import Path

TEMPLATE = (Path(__file__).parents[1] / "hitch" / "templates" / "map.html").read_text()


def test_menu_links_to_the_route_index():
    assert 'href="/route/index.html"' in TEMPLATE


def test_menu_links_to_why_not_hitchhike():
    assert 'href="/why-not-hitchhike"' in TEMPLATE
