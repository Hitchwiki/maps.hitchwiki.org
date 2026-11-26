"""Flask-Security upgrades (5.6 -> 5.8.1) must keep the password login working and must not
follow an off-site `next` (GHSA-w2j7-f3c6-g8cw, the open redirect 5.8.1 fixes)."""

import uuid
from urllib.parse import urlsplit

from flask_security import hash_password


def _make_user(app, db):
    name = f"fsuser{uuid.uuid4().hex[:8]}"
    ds = app.extensions["security"].datastore
    ds.create_user(username=name, email=f"{name}@example.invalid", password=hash_password("correct horse 42"), active=True)
    db.session.commit()
    return name


def test_password_login_redirects_to_me(app, client, db):
    name = _make_user(app, db)
    resp = client.post("/_fs/login", data={"username": name, "password": "correct horse 42"})
    assert resp.status_code == 302, resp.get_data(as_text=True)[:500]
    assert resp.headers["Location"].endswith("/me")


def test_wrong_password_does_not_log_in(app, client, db):
    name = _make_user(app, db)
    resp = client.post("/_fs/login", data={"username": name, "password": "wrong"})
    assert resp.status_code != 302 or not resp.headers["Location"].endswith("/me")


def test_offsite_next_is_not_followed(app, client, db):
    name = _make_user(app, db)
    for nxt in ("https://evil.example/", "//evil.example/", "/\\evil.example/"):
        resp = client.post(f"/_fs/login?next={nxt}", data={"username": name, "password": "correct horse 42"})
        loc = resp.headers.get("Location", "")
        # A browser treats a leading "/\\" like "//"; an encoded %5C is a harmless same-origin path.
        assert urlsplit(loc.replace("\\", "/")).netloc in ("", "localhost"), (nxt, loc)
