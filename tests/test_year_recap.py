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


def test_recap_link_year_only_in_december_and_early_january():
    from datetime import date

    from hitch.blueprints.user import _recap_link_year

    assert _recap_link_year(date(2026, 11, 30)) is None
    assert _recap_link_year(date(2026, 12, 1)) == 2026
    assert _recap_link_year(date(2027, 1, 15)) == 2026
    assert _recap_link_year(date(2027, 1, 16)) is None


def test_year_recap_image_is_png_and_404s_for_unknown_user(client):
    assert client.get("/insights/nobody-here-xyz/2026.png").status_code == 404
    assert client.get("/insights/nobody-here-xyz/1850.png").status_code == 404


def test_render_year_recap_png_bytes():
    from hitch.blueprints.user import _render_year_recap_png

    buf = _render_year_recap_png("tester", 2026, {"rides": 7, "km": 812.4, "waiting_min": 190, "areas": 3})
    assert buf.read(8) == b"\x89PNG\r\n\x1a\n"


def test_map_recap_pill_only_for_logged_in_in_season(app, client, monkeypatch):
    _user(app, "yrpill")
    monkeypatch.setattr("hitch.blueprints.user._recap_link_year", lambda today=None: 2026)
    assert b'id="recap-offer"' not in client.get("/").data
    with client.session_transaction() as sess:
        sess["_user_id"] = "yr-yrpill"
        sess["_fresh"] = True
    html = client.get("/").data
    assert b'id="recap-offer"' in html and b"/insights/yrpill/2026?ref=map-banner" in html
    monkeypatch.setattr("hitch.blueprints.user._recap_link_year", lambda today=None: None)
    assert b'id="recap-offer"' not in client.get("/").data
