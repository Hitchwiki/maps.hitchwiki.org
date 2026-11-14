from pathlib import Path

SRC = (Path(__file__).resolve().parent.parent / "hitch/templates/security/login_user.html").read_text()


def test_login_next_has_fixed_buckets():
    for b in ('"messages"', '"account"', '"routing"', '"other"'):
        assert b in SRC
