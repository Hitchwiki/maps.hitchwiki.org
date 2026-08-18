from hitch.blueprints.api_auth import APP_CALLBACK, finish_mobile_login
from hitch.extensions import db, security
from hitch.models import AppAuthCode


def _make_user(username="loginuser"):
    user = security.datastore.find_user(username=username)
    if user is None:
        user = security.datastore.create_user(
            username=username,
            email=f"{username}@x.oauth",
            password="x" * 12,
            hitchwiki_username=username,
        )
        db.session.commit()
    return user


def test_api_auth_login_redirects_to_hitchwiki_and_flags_mobile(client):
    resp = client.get("/api/auth/login")
    assert resp.status_code == 302
    assert "oauth2/authorize" in resp.headers["Location"]
    assert "state=" in resp.headers["Location"]
    with client.session_transaction() as sess:
        assert sess["oauth_mobile"] is True
        assert sess["oauth_state"]


def test_finish_mobile_login_mints_code_and_redirects_to_scheme(app):
    with app.app_context():
        db.create_all()
        user = _make_user()
        resp = finish_mobile_login(user)
        assert resp.status_code == 302
        loc = resp.headers["Location"]
        assert loc.startswith(APP_CALLBACK + "?code=")
        code = loc.split("code=", 1)[1]
        row = AppAuthCode.query.filter_by(code=code).first()
        assert row is not None and row.user_id == user.id
