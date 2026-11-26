"""/leaderboard must survive an erased account.

Self-serve deletion (account_erasure.py) keeps the user row with username = NULL. The
leaderboard lowercased every username, so one deletion 500'd the page for everybody.
"""

import hitch.blueprints.user as user_bp


def test_leaderboard_renders_with_erased_user(app, client, monkeypatch):
    from hitch.extensions import db as _db
    from hitch.models import User

    monkeypatch.setattr(user_bp, "_read_leaderboard_json", lambda name: [])
    with app.app_context():
        _db.session.add(
            User(username=None, email="deleted-x@deleted.invalid", password="x", active=False, fs_uniquifier="erased-lb")
        )
        _db.session.commit()
    try:
        r = client.get("/leaderboard")
        assert r.status_code == 200, r.get_data(as_text=True)[:400]
        assert "/account/None" not in r.get_data(as_text=True)
    finally:
        with app.app_context():
            _db.session.query(User).filter_by(fs_uniquifier="erased-lb").delete()
            _db.session.commit()
