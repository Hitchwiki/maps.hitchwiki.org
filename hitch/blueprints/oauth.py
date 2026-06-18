"""Hitchwiki OAuth2 login blueprint.

Replaces Flask-Security's built-in login/register with Hitchwiki OAuth2.
On first login, a local User record is auto-created using the Hitchwiki username.
"""

import secrets

import requests as http_requests
from flask import Blueprint, current_app, redirect, render_template, request, session, url_for
from flask_security import login_user, logout_user

from hitch.blueprints.utils.send_welcome_email import maybe_send_welcome_email
from hitch.extensions import db, security

oauth_bp = Blueprint("oauth", __name__)


def _wiki_base():
    return current_app.config["HITCHWIKI_WIKI_BASE"]


@oauth_bp.route("/login")
def login():
    """Show login page, or handle the OAuth callback if ?code= is present."""
    code = request.args.get("code")
    if code:
        return _handle_callback(code)

    return render_template("security/login_user.html")


@oauth_bp.route("/login/oauth")
def login_oauth():
    """Start the OAuth2 redirect to Hitchwiki."""
    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state

    authorize_url = f"{_wiki_base()}/rest.php/oauth2/authorize"
    params = {
        "response_type": "code",
        "client_id": current_app.config["HITCHWIKI_OAUTH_CLIENT_ID"],
        "redirect_uri": url_for("oauth.login", _external=True),
        "state": state,
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return redirect(f"{authorize_url}?{query}")


@oauth_bp.route("/register")
def register():
    """Registration is handled automatically on first OAuth login."""
    return redirect(url_for("oauth.login"))


@oauth_bp.route("/logout")
def logout():
    logout_user()
    session.clear()
    return redirect("/")


def _handle_callback(code):
    """Exchange authorization code for access token, fetch profile, login/create user."""
    state = request.args.get("state")
    if state != session.pop("oauth_state", None):
        return "State mismatch - possible CSRF attack", 403

    wiki_base = _wiki_base()
    token_url = f"{wiki_base}/rest.php/oauth2/access_token"
    redirect_uri = url_for("oauth.login", _external=True)

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
        return "Login failed: could not complete OAuth exchange. Please try again.", 400

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
        return "Login failed: could not fetch your Hitchwiki profile. Please try again.", 400

    profile = profile_response.json()
    hitchwiki_username = profile.get("username")
    email = profile.get("email")

    if not hitchwiki_username:
        return "Login failed: Hitchwiki did not return a username.", 400

    # Find or create local user
    user = security.datastore.find_user(username=hitchwiki_username)
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
        return redirect("/edit-user")

    # Existing user - just log in
    login_user(user, remember=True)
    # Existing users created before the welcome email shipped get it on this first
    # login after rollout; the gate ensures it's still sent at most once per user.
    maybe_send_welcome_email(user)
    return redirect("/me")
