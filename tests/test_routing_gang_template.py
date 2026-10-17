import re
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent.parent / "hitch" / "templates"


def _blocks(name):
    return set(re.findall(r"{%-?\s*block\s+(\w+)", (TEMPLATES / name).read_text()))


def test_routing_gang_only_fills_blocks_base_defines():
    # A child block base.html does not define is silently dropped: the page
    # returns 200 and renders only the header (the 2026-10-15 white screen).
    unknown = _blocks("routing_gang.html") - _blocks("base.html")
    assert not unknown, f"blocks not defined in base.html: {sorted(unknown)}"


def test_routing_gang_fills_the_body_block():
    assert "main" in _blocks("routing_gang.html")


def test_routing_gang_reads_landing_ref_not_stripped_query():
    # base.html strips ?ref= from the address bar before page scripts run, so
    # the opened event must read window.hmLandingRef, not location.search.
    src = (TEMPLATES / "routing_gang.html").read_text()
    assert "window.hmLandingRef" in src
    assert 'location.search.includes("ref=' not in src
