"""General chat belongs on Matrix; map-project discussion belongs on Signal."""

from pathlib import Path

ROOT = Path(__file__).parents[1]
INIT = (ROOT / "hitch" / "__init__.py").read_text()
MAP = (ROOT / "hitch" / "templates" / "map.html").read_text()
HELP = (ROOT / "hitch" / "templates" / "help.html").read_text()


def test_general_community_chat_uses_matrix():
    assert 'GENERAL_CHAT_URL = "https://matrix.to/#/#hitchhiking:hitchhiking.org"' in INIT
    assert 'link=\'<a href="\' ~ GENERAL_CHAT_URL' in MAP


def test_map_project_discussion_stays_on_signal():
    # 2 as of the empty-spot community-chat nudge (map.html #spot-empty-chat):
    # the pre-existing footer link, plus this second legitimate use of the
    # same routing rule (Signal, not Matrix, for map-project discussion).
    assert MAP.count("SIGNAL_CHAT_URL") == 2
    assert HELP.count("SIGNAL_CHAT_URL") == 3
