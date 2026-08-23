"""_send_via_sparkpost (hitch/blueprints/utils/send_welcome_email.py) is the one
shared helper behind three sends: the welcome email, the nearby-hitchhikers digest,
and the inactive-user reminder. All three had open_tracking/click_tracking hardcoded
off with no comment explaining why -- the same "no click/open data on our own email"
gap hitchhiking-newsletter's send_newsletter.py had, just in this app's own sends
instead. None of the three templates carry a one-click state-changing link (unlike
the newsletter's real unsubscribe URL), so there is no link-scanner-prefetch risk
in turning tracking on here.
"""

from hitch.blueprints.utils.send_welcome_email import _send_via_sparkpost


class _CapturingResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {"results": {"id": "test"}}


def test_sparkpost_options_have_tracking_enabled(app, monkeypatch):
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return _CapturingResponse()

    monkeypatch.setattr("hitch.blueprints.utils.send_welcome_email.requests.post", fake_post)

    with app.app_context():
        _send_via_sparkpost("test@example.com", "Test", "Subject", "<p>hi</p>", "hi")

    assert captured["json"]["options"]["open_tracking"] is True
    assert captured["json"]["options"]["click_tracking"] is True
