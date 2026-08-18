from datetime import datetime, timedelta

from hitch.blueprints.api_auth import create_app_auth_code
from hitch.extensions import db, security
from hitch.models import AppAuthCode


def _make_user(username="tokenuser"):
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


def test_token_exchange_returns_bearer_and_username(client, app):
    with app.app_context():
        db.create_all()
        user = _make_user()
        code = create_app_auth_code(user)
    resp = client.post("/api/auth/token", json={"code": code})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["username"] == "tokenuser"
    assert isinstance(body["token"], str) and body["token"]


def test_token_code_is_single_use(client, app):
    with app.app_context():
        db.create_all()
        code = create_app_auth_code(_make_user())
    assert client.post("/api/auth/token", json={"code": code}).status_code == 200
    # Reuse: the row was consumed, so a replay fails.
    assert client.post("/api/auth/token", json={"code": code}).status_code == 400


def test_token_rejects_expired_code(client, app):
    with app.app_context():
        db.create_all()
        code = create_app_auth_code(_make_user())
        row = AppAuthCode.query.filter_by(code=code).first()
        row.created_at = datetime.utcnow() - timedelta(minutes=6)
        db.session.commit()
    assert client.post("/api/auth/token", json={"code": code}).status_code == 400


def test_token_rejects_missing_and_unknown(client):
    assert client.post("/api/auth/token", json={}).status_code == 400
    assert client.post("/api/auth/token", json={"code": "nope"}).status_code == 400
