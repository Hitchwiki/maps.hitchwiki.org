"""The one-shot year-recap email: who is eligible, and what the rendered message says."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

import hitch.blueprints.utils.send_welcome_email as swe
from hitch.blueprints.utils.send_year_recap_email import eligible_users, send_year_recap_email
from hitch.extensions import db as _db
from hitch.models import User


def _u(name, **kw):
    base = dict(
        username=name,
        email=f"{name}@example.com",
        password="x",
        active=True,
        fs_uniquifier=f"yr-{name}",
        email_notifications=True,
        total_rides=3,
        last_ride_at=datetime(2026, 6, 1),
    )
    base.update(kw)
    return User(**base)


@pytest.fixture
def cohort(app):
    with app.app_context():
        _db.session.add_all(
            [
                _u("yr_ok"),
                _u("yr_optout", email_notifications=False),
                _u("yr_synthetic", email="x@hitchwiki.oauth"),
                _u("yr_last_year", last_ride_at=datetime(2025, 12, 31)),
                _u("yr_no_rides", total_rides=0, last_ride_at=None),
                _u("yr_already", recap_email_sent_year=2026),
            ]
        )
        _db.session.commit()
        yield
        User.query.filter(User.username.like("yr_%")).delete(synchronize_session=False)
        _db.session.commit()


def test_only_opted_in_real_2026_loggers_not_yet_mailed_are_eligible(app, cohort):
    with app.app_context():
        names = {u.username for u in eligible_users(2026) if u.username.startswith("yr_")}
    assert names == {"yr_ok"}


def test_recap_email_links_to_the_recap_with_ref_and_own_campaign(app, monkeypatch):
    captured = {}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"results": {"id": "t"}}

    def fake_post(url, headers, json, timeout):
        captured["json"] = json
        return _Resp()

    monkeypatch.setattr(swe.requests, "post", fake_post)
    user = MagicMock(email="t@example.com", username="Tramper")
    with app.test_request_context():
        send_year_recap_email(user, 2026)
    payload = captured["json"]
    assert payload["campaign_id"] == "year-recap-2026"
    assert "Your 2026 recap is ready" in str(payload)
    assert "/insights/Tramper/2026?ref=recap-email" in str(payload)


def test_ensure_user_columns_adds_column_once():
    from sqlalchemy import create_engine, inspect, text

    from hitch import ensure_user_columns

    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE user (id INTEGER PRIMARY KEY, email TEXT)"))
        conn.execute(text("INSERT INTO user (email) VALUES ('a@example.org')"))
    ensure_user_columns(engine)
    ensure_user_columns(engine)  # second call is a no-op
    assert "recap_email_sent_year" in {c["name"] for c in inspect(engine).get_columns("user")}
    with engine.begin() as conn:
        assert conn.execute(text("SELECT recap_email_sent_year FROM user")).scalar() is None
