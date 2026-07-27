from hitch.extensions import db, security


def _make_user(username="meuser"):
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


def test_me_returns_username_for_valid_bearer(client, app):
    with app.app_context():
        db.create_all()
        token = _make_user().get_auth_token()
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.get_json()["username"] == "meuser"


def test_me_rejects_bad_or_missing_token(client, app):
    with app.app_context():
        db.create_all()
        _make_user()
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "token-without-bearer"}).status_code == 401
