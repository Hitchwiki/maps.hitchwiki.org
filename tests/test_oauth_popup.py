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


def test_anonymous_prompt_source_survives_oauth_redirect(client):
    client.get("/login?source=anon-signup")
    with client.session_transaction() as sess:
        assert sess["signup_prompt_source"] == "anon-signup"


def test_unknown_login_source_is_not_stored(client):
    client.get("/login?source=made-up")
    with client.session_transaction() as sess:
        assert "signup_prompt_source" not in sess


def test_new_user_target_attributes_only_the_known_prompt():
    from hitch.blueprints.oauth import _new_user_target

    assert _new_user_target("anon-signup") == "/?welcome=1&signup_prompt=account-created"
    assert _new_user_target("made-up") == "/?welcome=1"
    assert _new_user_target(None) == "/?welcome=1"


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


def test_redirect_uri_defaults_to_request_origin(app):
    """Unset HITCHWIKI_OAUTH_REDIRECT_BASE -> unchanged behaviour (url_for + scheme)."""
    from hitch.blueprints.oauth import _redirect_uri

    app.config["HITCHWIKI_OAUTH_REDIRECT_BASE"] = None
    app.config["HITCHWIKI_OAUTH_REDIRECT_SCHEME"] = "http"
    with app.test_request_context("/", base_url="http://127.0.0.1:5001"):
        assert _redirect_uri() == "http://127.0.0.1:5001/login"


def test_redirect_uri_can_be_pinned_to_a_tunnel_origin(app):
    """A tunnel's hostname is never what url_for() would infer, so allow pinning it."""
    from hitch.blueprints.oauth import _redirect_uri

    app.config["HITCHWIKI_OAUTH_REDIRECT_BASE"] = "https://example.trycloudflare.com"
    try:
        # Request arrives on some other origin entirely; the pinned base still wins.
        with app.test_request_context("/", base_url="http://localhost:5001"):
            assert _redirect_uri() == "https://example.trycloudflare.com/login"
    finally:
        app.config["HITCHWIKI_OAUTH_REDIRECT_BASE"] = None


def test_redirect_uri_base_tolerates_a_trailing_slash(app):
    from hitch.blueprints.oauth import _redirect_uri

    app.config["HITCHWIKI_OAUTH_REDIRECT_BASE"] = "https://example.trycloudflare.com/"
    try:
        with app.test_request_context("/", base_url="http://localhost:5001"):
            assert _redirect_uri() == "https://example.trycloudflare.com/login"
    finally:
        app.config["HITCHWIKI_OAUTH_REDIRECT_BASE"] = None
