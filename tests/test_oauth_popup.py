"""The OAuth flow can complete in a popup, so the map page never unloads (issue #106)."""


def test_popup_flag_is_set_and_state_still_stored(client):
    resp = client.get("/login/oauth?popup=1")
    # Still redirects out to Hitchwiki — the popup is what follows it.
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess["oauth_popup"] is True
        assert sess["oauth_state"]


def test_plain_login_oauth_sets_no_popup_flag(client):
    client.get("/login/oauth")
    with client.session_transaction() as sess:
        assert "oauth_popup" not in sess


def test_popup_flag_is_cleared_by_a_later_full_page_login(client):
    """A stale flag must not turn a normal login into a popup-completion page."""
    client.get("/login/oauth?popup=1")
    client.get("/login/oauth")
    with client.session_transaction() as sess:
        assert "oauth_popup" not in sess


def test_finish_login_renders_postmessage_page_for_popup(app):
    """With the flag set, the flow ends in the closing page instead of a 302."""
    from hitch.blueprints.oauth import _finish_login

    with app.test_request_context("/login?code=abc"):
        from flask import session

        session["oauth_popup"] = True
        resp = _finish_login("/me", needs_profile=False)
        html = resp if isinstance(resp, str) else resp
        assert "hitchwiki-auth" in html
        # Never postMessage to a wildcard origin.
        assert '"*"' not in html
        assert "window.location.origin" in html
        # The flag is single-use.
        assert "oauth_popup" not in session


def test_finish_login_redirects_when_not_a_popup(app):
    from hitch.blueprints.oauth import _finish_login

    with app.test_request_context("/login?code=abc"):
        resp = _finish_login("/me", needs_profile=False)
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/me"


def test_finish_login_popup_carries_needs_profile(app):
    from hitch.blueprints.oauth import _finish_login

    with app.test_request_context("/login?code=abc"):
        from flask import session

        session["oauth_popup"] = True
        html = _finish_login("/edit-user", needs_profile=True)
        assert "true" in html.split("needsProfile:")[1].split("\n")[0]
