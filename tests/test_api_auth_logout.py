from hitch.extensions import db, security


def _make_user(username="logoutuser"):
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


def test_logout_revokes_token(client, app):
    with app.app_context():
        db.create_all()
        token = _make_user().get_auth_token()
    auth = {"Authorization": f"Bearer {token}"}
    # Token works before logout.
    assert client.get("/api/auth/me", headers=auth).status_code == 200
    assert client.post("/api/auth/logout", headers=auth).status_code == 200
    # After logout the uniquifier rotated, so the same token no longer resolves.
    assert client.get("/api/auth/me", headers=auth).status_code == 401


def test_logout_requires_valid_token(client):
    assert client.post("/api/auth/logout").status_code == 401
