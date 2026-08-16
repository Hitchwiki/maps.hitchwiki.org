"""Hitchwiki OAuth2 login blueprint.

Replaces Flask-Security's built-in login/register with Hitchwiki OAuth2.
On first login, a local User record is auto-created using the Hitchwiki username.
"""

import secrets
from urllib.parse import urlencode

import requests as http_requests
from flask import Blueprint, current_app, redirect, render_template, request, session, url_for
from flask_security import login_user, logout_user

from hitch.blueprints.utils.notifications import ensure_welcome_notification
from hitch.blueprints.utils.send_welcome_email import maybe_send_welcome_email
from hitch.extensions import db, security
from hitch.usernames import find_user_ci

oauth_bp = Blueprint("oauth", __name__)


def _wiki_base():
    return current_app.config["HITCHWIKI_WIKI_BASE"]


def _redirect_uri():
    """The OAuth callback URL, identical at /authorize and at the token exchange.

    Both steps must send the exact string registered on the consumer, or
    league/oauth2-server rejects it as "Client authentication failed" -- the same
    message it gives for an unknown client. The scheme can't be inferred from the
    request (see HITCHWIKI_OAUTH_REDIRECT_SCHEME in settings.py), so state it.

    HITCHWIKI_OAUTH_REDIRECT_BASE overrides the whole origin. Behind a tunnel, url_for()
    derives the origin from the request, which yields a hostname the consumer has never
    heard of; pinning the origin lets a tunnel URL be registered and used verbatim.
    """
    base = current_app.config.get("HITCHWIKI_OAUTH_REDIRECT_BASE")
    if base:
        return base.rstrip("/") + url_for("oauth.login")
    return url_for("oauth.login", _external=True, _scheme=current_app.config["HITCHWIKI_OAUTH_REDIRECT_SCHEME"])


@oauth_bp.route("/login")
def login():
    """Show login page, or handle the OAuth callback if ?code= is present."""
    code = request.args.get("code")
    if code:
        return _handle_callback(code)

    return render_template("security/login_user.html")


def _finish_login(target, needs_profile):
    """End the OAuth flow.

    A popup-initiated login (see login_oauth) must not navigate the popup to /me — the
    opener is the map, and it stays put. Render a page that hands the result back to the
    opener and closes itself. A normal full-page login redirects exactly as before.
    """
    if session.pop("oauth_popup", False):
        return render_template("security/oauth_popup_done.html", needs_profile=needs_profile)
    return redirect(target)


@oauth_bp.route("/login/oauth")
def login_oauth():
    """Start the OAuth2 redirect to Hitchwiki."""
    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state
    # Hitchwiki redirects back with only `code` and `state`, so nothing of ours survives
    # the round trip except the session — record here that the flow began in a popup.
    if request.args.get("popup"):
        session["oauth_popup"] = True
    else:
        session.pop("oauth_popup", None)

    authorize_url = f"{_wiki_base()}/rest.php/oauth2/authorize"
    params = {
        "response_type": "code",
        "client_id": current_app.config["HITCHWIKI_OAUTH_CLIENT_ID"],
        "redirect_uri": _redirect_uri(),
        "state": state,
    }
    return redirect(f"{authorize_url}?{urlencode(params)}")


@oauth_bp.route("/register")
def register():
    """Registration is handled automatically on first OAuth login."""
    return redirect(url_for("oauth.login"))


@oauth_bp.route("/logout")
def logout():
    # Clear our own session data first, THEN call logout_user(). logout_user() doesn't
    # delete the remember-me cookie inline -- it sets session["_remember"] = "clear", a
    # marker Flask-Login reads at response time to expire the cookie. Calling
    # session.clear() afterwards would wipe that marker, leaving the remember cookie alive
    # so the next request re-authenticates the user (the "logout didn't log me out" bug).
    session.clear()
    logout_user()
    return redirect("/")


def _oauth_error(message, status=400):
    """Render an OAuth failure so it reaches the user, not a bare error string.

    Issue #120's whole complaint: a state mismatch (usually just a stale
    session -- the login tab sat open too long, or was opened twice) left the
    visitor on "State mismatch - possible CSRF attack" with no styling, no
    explanation, and, in the popup flow, no way back to the app at all --
    account.js's message listener never fires because nothing was ever
    posted to the opener, so the popup just sits there orphaned.

    Popup flow: mirror _finish_login's success path (oauth_popup_done.html)
    -- post the failure to the opener over the same "hitchwiki-auth" channel
    and show the message in the popup itself, so the reader can actually see
    what happened before closing it themselves. Full-page flow: back to the
    login page with the message inline, so the login button is still one
    click away instead of a dead end.
    """
    if session.pop("oauth_popup", False):
        return render_template("security/oauth_popup_error.html", message=message)
    return render_template("security/login_user.html", oauth_error=message), status


def _handle_callback(code):
    """Exchange authorization code for access token, fetch profile, login/create user."""
    state = request.args.get("state")
    if state != session.pop("oauth_state", None):
        return _oauth_error("State mismatch - possible CSRF attack. Please try logging in again.", 403)

    wiki_base = _wiki_base()
    token_url = f"{wiki_base}/rest.php/oauth2/access_token"
    redirect_uri = _redirect_uri()

    token_response = http_requests.post(
        token_url,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": current_app.config["HITCHWIKI_OAUTH_CLIENT_ID"],
            "client_secret": current_app.config["HITCHWIKI_OAUTH_CLIENT_SECRET"],
        },
        headers={
            "User-Agent": "MapsHitchwikiOAuth/1.0 (https://maps.hitchwiki.org)",
            "Accept": "application/json",
        },
    )

    if token_response.status_code != 200:
        current_app.logger.error(f"OAuth token exchange failed: {token_response.status_code} {token_response.text}")
        return _oauth_error("Login failed: could not complete OAuth exchange. Please try again.")

    access_token = token_response.json()["access_token"]

    # Fetch user profile from Hitchwiki
    profile_url = f"{wiki_base}/rest.php/oauth2/resource/profile"
    profile_response = http_requests.get(
        profile_url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "MapsHitchwikiOAuth/1.0 (https://maps.hitchwiki.org)",
            "Accept": "application/json",
        },
    )

    if profile_response.status_code != 200:
        current_app.logger.error(f"OAuth profile fetch failed: {profile_response.status_code} {profile_response.text}")
        return _oauth_error("Login failed: could not fetch your Hitchwiki profile. Please try again.")

    profile = profile_response.json()
    hitchwiki_username = profile.get("username")
    email = profile.get("email")

    if not hitchwiki_username:
        return _oauth_error("Login failed: Hitchwiki did not return a username.")

    # Find or create local user. Matched case-insensitively (hitch/usernames.py): an
    # account created here from an earlier import or a differently-cased spelling is the
    # same person, and an exact match would silently create them a second, empty account.
    user = find_user_ci(hitchwiki_username)
    if user is None:
        user = security.datastore.create_user(
            username=hitchwiki_username,
            email=email or f"{hitchwiki_username}@hitchwiki.oauth",
            password=secrets.token_urlsafe(64),
            hitchwiki_username=hitchwiki_username,
            # New sign-ups are opted into the newsletter by default; they can opt out
            # later on the /edit-user page.
            email_notifications=True,
        )
        db.session.commit()
        current_app.logger.info(f"Created new user from Hitchwiki OAuth: {hitchwiki_username}")

        # Log in and redirect to profile setup
        login_user(user, remember=True)
        # First-ever login: send the one-time welcome email (gated + non-fatal).
        maybe_send_welcome_email(user)
        # Seed the default in-app welcome notification (idempotent).
        ensure_welcome_notification(user)
        # Brand-new user: only the callback knows this, so it rides the postMessage /
        # redirect rather than being re-derived later from the user row. The full-page
        # path lands on the map with ?welcome=1 so the first-run intro (welcome.js) runs
        # before the profile-setup form; the popup path opens the intro via postMessage.
        return _finish_login("/?welcome=1", needs_profile=True)

    # Existing user - just log in
    login_user(user, remember=True)
    # Existing users created before the welcome email shipped get it on this first
    # login after rollout; the gate ensures it's still sent at most once per user.
    maybe_send_welcome_email(user)
    # Back-fills the welcome notification for users who registered before notifications
    # existed; idempotent, so existing users get it exactly once.
    ensure_welcome_notification(user)
    return _finish_login("/me", needs_profile=False)
