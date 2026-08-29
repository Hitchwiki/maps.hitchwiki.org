"""The welcome email, the nearby-hitchhikers digest and the inactive-user reminder
all go through _send_via_sparkpost on the Hitchwiki SparkPost account the newsletter
also uses. Without a per-flow campaign_id the metrics API cannot tell them apart (or
apart from the newsletter), so each caller must tag its send.
"""

from unittest.mock import MagicMock

import hitch.blueprints.utils.send_welcome_email as swe
from hitch.blueprints.utils.send_inactive_reminder_email import send_inactive_reminder_email
from hitch.blueprints.utils.send_nearby_hitchhikers_email import send_nearby_hitchhikers_email
from hitch.blueprints.utils.send_welcome_email import _send_via_sparkpost, send_welcome_email


class _CapturingResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {"results": {"id": "test"}}


def _capture(app, monkeypatch, fn):
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["json"] = json
        return _CapturingResponse()

    monkeypatch.setattr(swe.requests, "post", fake_post)
    monkeypatch.setattr(swe, "render_template", lambda *a, **k: "body")
    with app.app_context():
        fn()
    return captured["json"]


def test_campaign_id_is_omitted_when_not_requested(app, monkeypatch):
    payload = _capture(app, monkeypatch, lambda: _send_via_sparkpost("t@example.com", "T", "S", "<p>h</p>", "h"))
    assert "campaign_id" not in payload


def test_each_app_send_carries_its_own_campaign_id(app, monkeypatch):
    user = MagicMock(email="t@example.com", username="T")

    assert _capture(app, monkeypatch, lambda: send_welcome_email(user))["campaign_id"] == "welcome-email"
    assert _capture(app, monkeypatch, lambda: send_nearby_hitchhikers_email(user, []))["campaign_id"] == "nearby-hitchhikers"
    assert _capture(app, monkeypatch, lambda: send_inactive_reminder_email(user, 7))["campaign_id"] == "inactive-user-reminder"
