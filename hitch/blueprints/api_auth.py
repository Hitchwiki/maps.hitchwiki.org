"""Mobile bearer-token auth API (additive; the web session flow is untouched).

One-time-code OAuth: /api/auth/login starts the existing Hitchwiki exchange with a mobile
flag; the shared callback mints an AppAuthCode and redirects it to the app via a custom
scheme; the app exchanges it at /api/auth/token for a Flask-Security bearer token.
"""

import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode

from flask import Blueprint, current_app, jsonify, redirect, request, session

from hitch.blueprints.oauth import _redirect_uri, _wiki_base
from hitch.extensions import db
from hitch.models import AppAuthCode, User

api_auth_bp = Blueprint("api_auth", __name__)

# The app registers an intent-filter for this scheme and captures the ?code=.
APP_CALLBACK = "hitchwiki-app://oauth-callback"

# A code older than this is treated as expired (still consumed, so it can't be retried).
CODE_TTL = timedelta(minutes=5)


def create_app_auth_code(user):
    """Mint a single-use code for `user` and persist it."""
    code = secrets.token_urlsafe(32)
    db.session.add(AppAuthCode(code=code, user_id=user.id))
    db.session.commit()
    return code


def finish_mobile_login(user):
    """End a mobile OAuth flow: hand the app a one-time code via the custom scheme."""
    code = create_app_auth_code(user)
    return redirect(f"{APP_CALLBACK}?code={code}")


@api_auth_bp.route("/api/auth/login")
def api_login():
    """Start the mobile OAuth flow. Same authorize redirect as oauth.login_oauth, but flagged
    mobile so the shared callback finishes via finish_mobile_login instead of a session."""
    state = secrets.token_urlsafe(32)
    # oauth_state must be set exactly as login_oauth does so the shared callback's CSRF check passes.
    session["oauth_state"] = state
    session["oauth_mobile"] = True
    params = {
        "response_type": "code",
        "client_id": current_app.config["HITCHWIKI_OAUTH_CLIENT_ID"],
        "redirect_uri": _redirect_uri(),
        "state": state,
    }
    return redirect(f"{_wiki_base()}/rest.php/oauth2/authorize?{urlencode(params)}")


def consume_app_auth_code(code):
    """Return the code's user if the code exists and is fresh, else None. Always deletes the
    row (single-use), so neither a replay nor an expired retry can mint a token."""
    row = AppAuthCode.query.filter_by(code=code).first()
    if row is None:
        return None
    fresh = datetime.utcnow() - row.created_at < CODE_TTL
    user = db.session.get(User, row.user_id) if fresh else None
    db.session.delete(row)
    db.session.commit()
    return user


@api_auth_bp.route("/api/auth/token", methods=["POST"])
def api_token():
    code = (request.get_json(silent=True) or {}).get("code")
    if not code:
        return jsonify(error="missing code"), 400
    user = consume_app_auth_code(code)
    if user is None:
        return jsonify(error="invalid or expired code"), 400
    return jsonify(token=user.get_auth_token(), username=user.username)
