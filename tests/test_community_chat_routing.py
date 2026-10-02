"""Every community-chat link on the site goes to the Matrix room, and is tracked."""

import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
INIT = (ROOT / "hitch" / "__init__.py").read_text()
TEMPLATES = ROOT / "hitch" / "templates"
MAP = (TEMPLATES / "map.html").read_text()
HELP = (TEMPLATES / "help.html").read_text()
BASE = (TEMPLATES / "base.html").read_text()


def test_chat_url_is_the_matrix_room():
    assert 'GENERAL_CHAT_URL = "https://matrix.to/#/#hitchhiking:hitchhiking.org"' in INIT


def test_no_template_links_to_the_signal_group():
    # Till, 2026-10-02: the map links to the Matrix chat, not the Signal group.
    assert "SIGNAL_CHAT_URL" not in INIT
    for path in TEMPLATES.rglob("*.html"):
        text = path.read_text()
        assert "SIGNAL_CHAT_URL" not in text, path
        assert "signal.group" not in text, path


def test_every_chat_link_is_tracked_with_a_place():
    # 4 links on the map page (empty spot, menu, route sheet, ride saved), 3 on /help.
    for text, n in ((MAP, 4), (HELP, 3)):
        links = re.findall(r"<a[^>]*GENERAL_CHAT_URL[^>]*>", text)
        assert len(links) == n
        assert all("data-chat-place=" in a for a in links), links
    assert '"community_chat_click"' in BASE
    assert "chat_cohort" in BASE


def test_popup_login_updates_the_chat_cohort():
    # The OAuth popup keeps the map loaded, so the server-rendered cohort goes stale;
    # account.js must update the global the click listener reads.
    assert "cohort: window.hmChatCohort" in BASE
    account = (ROOT / "hitch" / "static" / "account.js").read_text()
    assert 'window.hmChatCohort = e.data.needsProfile ? "new" : "member"' in account
