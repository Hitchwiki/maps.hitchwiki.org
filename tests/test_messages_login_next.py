from pathlib import Path

SRC = (Path(__file__).resolve().parent.parent / "hitch" / "blueprints" / "messages.py").read_text()


def test_anonymous_redirects_keep_next():
    # IDEAS #1487: both login walls carry the return path (and so ?ref= attribution).
    assert SRC.count('"next": request.full_path.rstrip("?")') == 2
    assert 'redirect("/login")' not in SRC
