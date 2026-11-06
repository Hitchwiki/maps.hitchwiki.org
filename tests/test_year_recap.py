"""Year recap page (IDEAS #1279): counts rides by the year they were hitched."""

from hitch.extensions import db as _db
from hitch.models import User


def _user(app, name):
    with app.app_context():
        u = User(username=name, email=f"{name}@example.com", password="x", active=True, fs_uniquifier=f"yr-{name}")
        _db.session.add(u)
        _db.session.commit()
        return u.id


def test_unknown_user_redirects(client):
    assert client.get("/insights/nobody-yr/2026").status_code == 302


def test_absurd_year_is_404(client):
    assert client.get("/insights/anyone/1234").status_code == 404


def test_recap_page_renders_for_user_without_rides(app, client):
    uid = _user(app, "yrtester")
    try:
        resp = client.get("/insights/yrtester/2026")
        assert resp.status_code == 200
        assert b"2026" in resp.data
        assert b"No rides logged" in resp.data
    finally:
        with app.app_context():
            _db.session.delete(_db.session.get(User, uid))
            _db.session.commit()
