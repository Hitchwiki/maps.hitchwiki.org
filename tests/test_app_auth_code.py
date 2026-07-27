from datetime import datetime

from hitch.extensions import db, security
from hitch.models import AppAuthCode


def _make_user(username="t1"):
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


def test_app_auth_code_persists_and_links_user(app):
    with app.app_context():
        db.create_all()
        user = _make_user("t1")
        row = AppAuthCode(code="abc123", user_id=user.id)
        db.session.add(row)
        db.session.commit()

        got = AppAuthCode.query.filter_by(code="abc123").first()
        assert got is not None
        assert got.user_id == user.id
        assert isinstance(got.created_at, datetime)
