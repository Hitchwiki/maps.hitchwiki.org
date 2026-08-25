"""
Test script for Hitchwiki MediaWiki OAuth 2.0 login.

Usage:
    pip install flask requests
    python test_hitchwiki_oauth2.py

Then visit http://localhost:5001/login

NOTE: The OAuth consumer callback is set to https://maps.hitchwiki.org/login.
For local testing, either:
  1. Add "127.0.0.1 maps.hitchwiki.org" to /etc/hosts and use HTTPS (complex), or
  2. Update the consumer's callback URL to http://localhost:5001/login (easiest for testing), or
  3. After authorizing, manually copy the ?code=... from the redirect URL and paste it
     into http://localhost:5001/login?code=<CODE>
"""

import os
import secrets

from flask import Flask, redirect, request, session, url_for

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# Hitchwiki OAuth 2.0 credentials (from .env or environment)
CLIENT_ID = os.getenv("HITCHWIKI_OAUTH_CLIENT_ID")
CLIENT_SECRET = os.getenv("HITCHWIKI_OAUTH_CLIENT_SECRET")

# MediaWiki OAuth 2.0 endpoints
WIKI_BASE = os.getenv("HITCHWIKI_WIKI_BASE", "https://hitchwiki.org/en")
AUTHORIZE_URL = f"{WIKI_BASE}/rest.php/oauth2/authorize"
TOKEN_URL = f"{WIKI_BASE}/rest.php/oauth2/access_token"
PROFILE_URL = f"{WIKI_BASE}/rest.php/oauth2/resource/profile"


@app.route("/")
def index():
    if "user" in session:
        user = session["user"]
        return f'<h1>Logged in as {user.get("username", "unknown")}</h1><pre>{user}</pre><a href="/logout">Logout</a>'
    return '<h1>Hitchwiki OAuth 2.0 Test</h1><a href="/login">Login with Hitchwiki</a>'


@app.route("/login")
def login():
    # If we got a code back from the OAuth redirect, exchange it
    code = request.args.get("code")
    if code:
        return handle_callback(code)

    # Otherwise, start the OAuth flow
    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state

    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": request.url_rule and url_for("login", _external=True) or "https://maps.hitchwiki.org/login",
        "state": state,
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    auth_url = f"{AUTHORIZE_URL}?{query}"

    print(f"\n→ Redirecting to: {auth_url}\n")
    return redirect(auth_url)


def handle_callback(code):
    import requests

    # Verify state to prevent CSRF
    state = request.args.get("state")
    if state != session.get("oauth_state"):
        return "State mismatch - possible CSRF attack", 403

    # Exchange authorization code for access token
    redirect_uri = url_for("login", _external=True)
    token_response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
        headers={
            "User-Agent": "MapsHitchwikiOAuth/1.0 (https://maps.hitchwiki.org)",
            "Accept": "application/json",
        },
    )

    print(f"\n→ Token POST to: {TOKEN_URL}")
    print(f"→ Response URL: {token_response.url}")
    print(f"→ Token response ({token_response.status_code}): {token_response.text[:500]}\n")

    if token_response.status_code != 200:
        return f"<h1>Token exchange failed</h1><pre>{token_response.status_code}\n{token_response.text}</pre>", 400

    token_data = token_response.json()
    access_token = token_data["access_token"]

    # Fetch user profile
    profile_response = requests.get(
        PROFILE_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "MapsHitchwikiOAuth/1.0 (https://maps.hitchwiki.org)",
            "Accept": "application/json",
        },
    )

    print(f"\n→ Profile response ({profile_response.status_code}): {profile_response.text[:500]}\n")

    if profile_response.status_code == 200 and profile_response.text:
        try:
            session["user"] = profile_response.json()
        except Exception:
            session["user"] = {"note": "profile JSON parse failed", "raw": profile_response.text[:200]}
    else:
        session["user"] = {"note": f"profile fetch returned {profile_response.status_code}", "raw": profile_response.text[:200]}

    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


if __name__ == "__main__":
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # allow HTTP for local testing
    app.run(debug=True, host="0.0.0.0", port=5001)
