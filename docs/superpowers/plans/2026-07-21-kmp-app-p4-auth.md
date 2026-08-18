# KMP App P4 — Auth (mobile OAuth + bearer token) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an Android user sign in with Hitchwiki via the system browser, receive and securely store a bearer token, validate it on launch, see their identity, and log out — establishing the identity P5 (ride write) will need.

**Architecture:** A one-time-code OAuth flow. New Flask endpoints under `/api/auth/` reuse the existing Hitchwiki OAuth exchange, then hand the app a short-lived single-use code via a custom-scheme redirect; the app exchanges that code for a Flask-Security bearer token (JSON body, never in a URL). The token is minted by `user.get_auth_token()` and verified with `flask_security.utils.parse_auth_token`; logout revokes it by rotating `fs_uniquifier`. On the app side, `AuthRepository` orchestrates over three seams — `HitchwikiApi` (Ktor), `TokenStore` (EncryptedSharedPreferences), and `AuthController` (Custom Tabs + redirect Activity) — feeding a plain-class `AccountViewModel` behind an Account screen reached from an icon in the map top bar.

**Tech Stack:** Flask + Flask-Security-Too 5.6.2 (backend); Kotlin Multiplatform, Compose Multiplatform, Ktor (MockEngine for tests), androidx.browser (Custom Tabs), androidx.security:security-crypto (EncryptedSharedPreferences), kotlinx-coroutines/serialization.

## Global Constraints

- **Additive backend only.** All new Python lives under `/api/auth/`; the existing web session OAuth flow (`hitch/blueprints/oauth.py`) stays behaviourally identical except for a two-line mobile branch. Never change the web redirect/response behaviour.
- **Backend tests are pytest** in `tests/`, run with `python -m pytest tests/ -v`. The app is created via `create_app("testing")`; use the `client`/`app`/`db` fixtures in `tests/conftest.py`.
- **New DB column/table needs a manual prod migration** (no Alembic). Adding `AppAuthCode` requires the `ALTER TABLE`/`create_all` step per CLAUDE.md → "Database migrations". Call it out; do not run it against prod as part of this plan.
- **Android is the run/test target; iOS stays a compiling stub.** All app logic (repository, view model, DTOs) is commonMain; only the EncryptedSharedPreferences store, the Custom Tabs controller, and the redirect Activity are androidMain. iOS needs no auth actuals (nothing in commonMain constructs the Android impls).
- **Build discipline (memory-constrained host):** each KMP task runs `:composeApp:assembleDebug` and/or `:composeApp:testDebugUnitTest` ONLY. The single iOS guard `:composeApp:compileKotlinIosSimulatorArm64` runs ONCE at the end (Task 10). `gradle.properties` caps daemons to 1G / parallel off — do not change it.
- **Strict JSON:** models parse with `appJson` (`ignoreUnknownKeys = true`, not lenient). DTO field names/types must match the backend JSON exactly.
- **Plain-class ViewModels** (not `androidx.lifecycle.ViewModel`): constructor takes its data source(s), a `CoroutineScope`, and an injected `workDispatcher: CoroutineDispatcher = Dispatchers.Default` so tests pass `StandardTestDispatcher(testScheduler)` and `advanceUntilIdle()` stays deterministic.
- **Custom scheme:** `hitchwiki-app://oauth-callback`. **Backend base URL** the app talks to is `HitchwikiApi.BASE_URL` (`https://maps.hitchwiki.org`); the on-device end-to-end test needs that backend to already carry the P4 endpoints (deploy backend Tasks 1–5 first, or point the app at a dev backend).
- Work stays LOCAL on branch `feature/kmp-mobile-app`; do not push.

**Spec:** `docs/superpowers/specs/2026-07-21-kmp-app-p4-auth-design.md`

---

### Task 1: `AppAuthCode` model

The single-use bridge between the OAuth callback and the token exchange. Not the durable credential — it maps a short-lived code to a user for one `/api/auth/token` call.

**Files:**
- Modify: `hitch/models.py` (add the model near the other small models)
- Test: `tests/test_app_auth_code.py`

**Interfaces:**
- Produces: `AppAuthCode(id, code: str UNIQUE, user_id: int FK user.id, created_at: datetime)` — `created_at` defaults to `datetime.utcnow` (Python-side, so TTL math is consistent).

- [ ] **Step 1: Write the failing test**

Create `tests/test_app_auth_code.py`:
```python
from datetime import datetime

from hitch.extensions import db, security
from hitch.models import AppAuthCode


def _make_user(username="t1"):
    user = security.datastore.find_user(username=username)
    if user is None:
        user = security.datastore.create_user(
            username=username, email=f"{username}@x.oauth", password="x" * 12,
            hitchwiki_username=username,
        )
        db.session.commit()
    return user


def test_app_auth_code_persists_and_links_user(app):
    with app.app_context():
        db.create_all()
        user = _make_user("t1")
        row = AppAuthCode(code="abc123", user_id=user.id)
        db.session.add(row)
        db.session.commit()

        got = AppAuthCode.query.filter_by(code="abc123").first()
        assert got is not None
        assert got.user_id == user.id
        assert isinstance(got.created_at, datetime)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_app_auth_code.py -v`
Expected: FAIL — `ImportError: cannot import name 'AppAuthCode'`.

- [ ] **Step 3: Implement the model**

In `hitch/models.py`, add the import at the top if absent and the model after the `Notification` model:
```python
from datetime import datetime  # add to the existing imports if not present


class AppAuthCode(db.Model):
    """Single-use, short-lived code bridging the mobile OAuth callback to /api/auth/token.

    The callback mints one of these and redirects it to the app via the custom scheme; the
    app exchanges it for a bearer token. Consumed (deleted) on first use so a replayed
    redirect can't mint a second token. Not the durable credential.
    """

    __tablename__ = "app_auth_code"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_app_auth_code.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hitch/models.py tests/test_app_auth_code.py
git commit -m "feat(api-auth): AppAuthCode single-use code model"
```

**Prod migration (record, do NOT run here):** after deploy, the prod DB needs the new table. `db.create_all()` adds *missing tables* (unlike columns), so a container restart that runs `flask init` creates it; otherwise run once:
```bash
sudo docker exec hitchhiking-map python3 -c "
import sqlite3
c = sqlite3.connect('/app/db/hitchhiking-prod.sqlite')
c.execute('CREATE TABLE IF NOT EXISTS app_auth_code (id INTEGER PRIMARY KEY, code VARCHAR(64) UNIQUE NOT NULL, user_id INTEGER NOT NULL, created_at DATETIME NOT NULL)')
c.execute('CREATE UNIQUE INDEX IF NOT EXISTS ix_app_auth_code_code ON app_auth_code (code)')
c.commit(); c.close()
"
```

---

### Task 2: `/api/auth/login` + mobile callback branch

The mobile OAuth entry point and the redirect that hands the app a one-time code. Reuses the existing Hitchwiki authorize redirect and the existing callback's find/create-user logic.

**Files:**
- Create: `hitch/blueprints/api_auth.py`
- Modify: `hitch/blueprints/oauth.py` (two-line mobile branch at the two callback return sites)
- Modify: `hitch/__init__.py` (import + register the blueprint)
- Test: `tests/test_api_auth_login.py`

**Interfaces:**
- Consumes: `hitch.blueprints.oauth._wiki_base`, `hitch.blueprints.oauth._redirect_uri`; `AppAuthCode` (Task 1).
- Produces: blueprint `api_auth_bp`; route `GET /api/auth/login`; `create_app_auth_code(user) -> str`; `finish_mobile_login(user) -> Response` (302 to `hitchwiki-app://oauth-callback?code=<code>`); constant `APP_CALLBACK = "hitchwiki-app://oauth-callback"`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_api_auth_login.py`:
```python
from hitch.blueprints.api_auth import APP_CALLBACK, finish_mobile_login
from hitch.extensions import db, security
from hitch.models import AppAuthCode


def _make_user(username="loginuser"):
    user = security.datastore.find_user(username=username)
    if user is None:
        user = security.datastore.create_user(
            username=username, email=f"{username}@x.oauth", password="x" * 12,
            hitchwiki_username=username,
        )
        db.session.commit()
    return user


def test_api_auth_login_redirects_to_hitchwiki_and_flags_mobile(client):
    resp = client.get("/api/auth/login")
    assert resp.status_code == 302
    assert "oauth2/authorize" in resp.headers["Location"]
    assert "state=" in resp.headers["Location"]
    with client.session_transaction() as sess:
        assert sess["oauth_mobile"] is True
        assert sess["oauth_state"]


def test_finish_mobile_login_mints_code_and_redirects_to_scheme(app):
    with app.app_context():
        db.create_all()
        user = _make_user()
        resp = finish_mobile_login(user)
        assert resp.status_code == 302
        loc = resp.headers["Location"]
        assert loc.startswith(APP_CALLBACK + "?code=")
        code = loc.split("code=", 1)[1]
        row = AppAuthCode.query.filter_by(code=code).first()
        assert row is not None and row.user_id == user.id
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_api_auth_login.py -v`
Expected: FAIL — `ModuleNotFoundError: hitch.blueprints.api_auth`.

- [ ] **Step 3: Create the blueprint**

Create `hitch/blueprints/api_auth.py`:
```python
"""Mobile bearer-token auth API (additive; the web session flow is untouched).

One-time-code OAuth: /api/auth/login starts the existing Hitchwiki exchange with a mobile
flag; the shared callback mints an AppAuthCode and redirects it to the app via a custom
scheme; the app exchanges it at /api/auth/token for a Flask-Security bearer token.
"""

import secrets
from urllib.parse import urlencode

from flask import Blueprint, current_app, redirect, session

from hitch.blueprints.oauth import _redirect_uri, _wiki_base
from hitch.extensions import db
from hitch.models import AppAuthCode

api_auth_bp = Blueprint("api_auth", __name__)

# The app registers an intent-filter for this scheme and captures the ?code=.
APP_CALLBACK = "hitchwiki-app://oauth-callback"


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
```

- [ ] **Step 4: Wire the mobile branch into the shared callback**

In `hitch/blueprints/oauth.py`, inside `_handle_callback`, add the mobile branch at BOTH existing return sites. The new-user branch — change:
```python
        return _finish_login("/?welcome=1", needs_profile=True)
```
to:
```python
        # Mobile clients finish via a one-time code + custom-scheme redirect, not a session.
        # login_user above set a cookie the app simply ignores, which is harmless.
        if session.pop("oauth_mobile", False):
            from hitch.blueprints.api_auth import finish_mobile_login
            return finish_mobile_login(user)
        return _finish_login("/?welcome=1", needs_profile=True)
```
And the existing-user branch — change:
```python
    return _finish_login("/me", needs_profile=False)
```
to:
```python
    if session.pop("oauth_mobile", False):
        from hitch.blueprints.api_auth import finish_mobile_login
        return finish_mobile_login(user)
    return _finish_login("/me", needs_profile=False)
```
(The import is function-local to avoid a circular import at module load: `api_auth` imports from `oauth`.)

- [ ] **Step 5: Register the blueprint**

In `hitch/__init__.py`, add the import beside the others (after `from hitch.blueprints.oauth import oauth_bp`):
```python
from hitch.blueprints.api_auth import api_auth_bp
```
and register it in `register_blueprints`, after `app.register_blueprint(oauth_bp)`:
```python
    app.register_blueprint(api_auth_bp)
```

- [ ] **Step 6: Run to verify it passes**

Run: `python -m pytest tests/test_api_auth_login.py -v`
Expected: PASS (both tests).

- [ ] **Step 7: Guard against web-flow regression**

Run: `python -m pytest tests/ -v -k "oauth or login or auth"`
Expected: PASS (existing OAuth/web tests unaffected by the additive branch).

- [ ] **Step 8: Commit**

```bash
git add hitch/blueprints/api_auth.py hitch/blueprints/oauth.py hitch/__init__.py tests/test_api_auth_login.py
git commit -m "feat(api-auth): /api/auth/login + one-time-code mobile callback branch"
```

---

### Task 3: `/api/auth/token`

Exchange a one-time code for a Flask-Security bearer token. Single-use: the code is consumed (deleted) whether or not it was still fresh.

**Files:**
- Modify: `hitch/blueprints/api_auth.py`
- Test: `tests/test_api_auth_token.py`

**Interfaces:**
- Consumes: `AppAuthCode`, `create_app_auth_code`; `user.get_auth_token()`.
- Produces: `consume_app_auth_code(code: str) -> User | None`; route `POST /api/auth/token` accepting `{"code": str}`, returning `{"token": str, "username": str}` (200) or `{"error": str}` (400).

- [ ] **Step 1: Write the failing test**

Create `tests/test_api_auth_token.py`:
```python
from datetime import datetime, timedelta

from hitch.blueprints.api_auth import create_app_auth_code
from hitch.extensions import db, security
from hitch.models import AppAuthCode


def _make_user(username="tokenuser"):
    user = security.datastore.find_user(username=username)
    if user is None:
        user = security.datastore.create_user(
            username=username, email=f"{username}@x.oauth", password="x" * 12,
            hitchwiki_username=username,
        )
        db.session.commit()
    return user


def test_token_exchange_returns_bearer_and_username(client, app):
    with app.app_context():
        db.create_all()
        user = _make_user()
        code = create_app_auth_code(user)
    resp = client.post("/api/auth/token", json={"code": code})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["username"] == "tokenuser"
    assert isinstance(body["token"], str) and body["token"]


def test_token_code_is_single_use(client, app):
    with app.app_context():
        db.create_all()
        code = create_app_auth_code(_make_user())
    assert client.post("/api/auth/token", json={"code": code}).status_code == 200
    # Reuse: the row was consumed, so a replay fails.
    assert client.post("/api/auth/token", json={"code": code}).status_code == 400


def test_token_rejects_expired_code(client, app):
    with app.app_context():
        db.create_all()
        code = create_app_auth_code(_make_user())
        row = AppAuthCode.query.filter_by(code=code).first()
        row.created_at = datetime.utcnow() - timedelta(minutes=6)
        db.session.commit()
    assert client.post("/api/auth/token", json={"code": code}).status_code == 400


def test_token_rejects_missing_and_unknown(client):
    assert client.post("/api/auth/token", json={}).status_code == 400
    assert client.post("/api/auth/token", json={"code": "nope"}).status_code == 400
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_api_auth_token.py -v`
Expected: FAIL — 404 (route missing) so the 200 assertions fail.

- [ ] **Step 3: Implement**

In `hitch/blueprints/api_auth.py`, add the imports and code:
```python
from datetime import datetime, timedelta

from flask import jsonify, request

from hitch.models import User
```
```python
# A code older than this is treated as expired (still consumed, so it can't be retried).
CODE_TTL = timedelta(minutes=5)


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
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_api_auth_token.py -v`
Expected: PASS (all four).

- [ ] **Step 5: Commit**

```bash
git add hitch/blueprints/api_auth.py tests/test_api_auth_token.py
git commit -m "feat(api-auth): /api/auth/token one-time-code exchange"
```

---

### Task 4: `/api/auth/me` + Bearer verification helper

Validate a bearer token and return the username. This is what the app calls on launch and to display identity.

**Files:**
- Modify: `hitch/blueprints/api_auth.py`
- Test: `tests/test_api_auth_me.py`

**Interfaces:**
- Consumes: `flask_security.utils.parse_auth_token`, `security.datastore.find_user`, `user.get_auth_token()`.
- Produces: `user_from_bearer() -> User | None`; route `GET /api/auth/me` returning `{"username": str}` (200) or `{"error": str}` (401).

- [ ] **Step 1: Write the failing test**

Create `tests/test_api_auth_me.py`:
```python
from hitch.extensions import db, security


def _make_user(username="meuser"):
    user = security.datastore.find_user(username=username)
    if user is None:
        user = security.datastore.create_user(
            username=username, email=f"{username}@x.oauth", password="x" * 12,
            hitchwiki_username=username,
        )
        db.session.commit()
    return user


def test_me_returns_username_for_valid_bearer(client, app):
    with app.app_context():
        db.create_all()
        token = _make_user().get_auth_token()
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.get_json()["username"] == "meuser"


def test_me_rejects_bad_or_missing_token(client, app):
    with app.app_context():
        db.create_all()
        _make_user()
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "token-without-bearer"}).status_code == 401
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_api_auth_me.py -v`
Expected: FAIL — 404 (route missing).

- [ ] **Step 3: Implement**

In `hitch/blueprints/api_auth.py`, add:
```python
from flask_security.utils import parse_auth_token

from hitch.extensions import db, security  # `security` added to the existing extensions import
```
```python
def user_from_bearer():
    """Resolve the user from an `Authorization: Bearer <token>` header, or None.

    Flask-Security's own header is `Authentication-Token`, not `Authorization: Bearer`, so we
    verify the token directly: parse_auth_token validates the signature/expiry and yields the
    fs_uniquifier (`uid`); find_user resolves it. Logout rotates fs_uniquifier, so a revoked
    token's uid no longer matches any user and this returns None.
    """
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    try:
        tdata = parse_auth_token(header[len("Bearer "):])
    except Exception:
        return None
    user = security.datastore.find_user(fs_uniquifier=tdata["uid"])
    if user is None or not user.active:
        return None
    return user


@api_auth_bp.route("/api/auth/me")
def api_me():
    user = user_from_bearer()
    if user is None:
        return jsonify(error="unauthorized"), 401
    return jsonify(username=user.username)
```
(If `from hitch.extensions import db` is already present at the top of the file, extend it to `from hitch.extensions import db, security` rather than adding a second import line.)

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_api_auth_me.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hitch/blueprints/api_auth.py tests/test_api_auth_me.py
git commit -m "feat(api-auth): /api/auth/me bearer verification"
```

---

### Task 5: `/api/auth/logout`

Revoke the bearer token server-side by rotating `fs_uniquifier`.

**Files:**
- Modify: `hitch/blueprints/api_auth.py`
- Test: `tests/test_api_auth_logout.py`

**Interfaces:**
- Consumes: `user_from_bearer` (Task 4); `security.datastore.set_uniquifier`.
- Produces: route `POST /api/auth/logout` returning `{"status": "ok"}` (200) or `{"error": str}` (401).

- [ ] **Step 1: Write the failing test**

Create `tests/test_api_auth_logout.py`:
```python
from hitch.extensions import db, security


def _make_user(username="logoutuser"):
    user = security.datastore.find_user(username=username)
    if user is None:
        user = security.datastore.create_user(
            username=username, email=f"{username}@x.oauth", password="x" * 12,
            hitchwiki_username=username,
        )
        db.session.commit()
    return user


def test_logout_revokes_token(client, app):
    with app.app_context():
        db.create_all()
        token = _make_user().get_auth_token()
    auth = {"Authorization": f"Bearer {token}"}
    # Token works before logout.
    assert client.get("/api/auth/me", headers=auth).status_code == 200
    assert client.post("/api/auth/logout", headers=auth).status_code == 200
    # After logout the uniquifier rotated, so the same token no longer resolves.
    assert client.get("/api/auth/me", headers=auth).status_code == 401


def test_logout_requires_valid_token(client):
    assert client.post("/api/auth/logout").status_code == 401
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_api_auth_logout.py -v`
Expected: FAIL — 404 on the logout POST.

- [ ] **Step 3: Implement**

In `hitch/blueprints/api_auth.py`, add:
```python
@api_auth_bp.route("/api/auth/logout", methods=["POST"])
def api_logout():
    user = user_from_bearer()
    if user is None:
        return jsonify(error="unauthorized"), 401
    # Rotating fs_uniquifier invalidates every bearer token minted for this user.
    security.datastore.set_uniquifier(user)
    db.session.commit()
    return jsonify(status="ok")
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_api_auth_logout.py -v && python -m pytest tests/ -q`
Expected: PASS (logout tests + the whole suite green).

- [ ] **Step 5: Commit**

```bash
git add hitch/blueprints/api_auth.py tests/test_api_auth_logout.py
git commit -m "feat(api-auth): /api/auth/logout revokes via fs_uniquifier rotation"
```

---

### Task 6: `HitchwikiApi` auth methods + DTOs

The Ktor calls the app makes: exchange code, validate token, logout.

**Files:**
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/model/AuthDtos.kt`
- Modify: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/data/HitchwikiApi.kt`
- Test: `mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/data/HitchwikiApiAuthTest.kt`

**Interfaces:**
- Produces: `@Serializable data class TokenRequest(val code: String)`, `TokenResponse(val token: String, val username: String)`, `MeResponse(val username: String)`; `HitchwikiApi.authToken(code): TokenResponse`, `authMe(token): MeResponse`, `authLogout(token)`.

- [ ] **Step 1: Write the failing test**

Create `mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/data/HitchwikiApiAuthTest.kt`:
```kotlin
package org.hitchwiki.maps.data
import io.ktor.client.engine.mock.*
import io.ktor.http.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.*
import kotlin.test.*

class HitchwikiApiAuthTest {
    private fun api(handler: MockRequestHandleScope.(io.ktor.client.request.HttpRequestData) -> HttpResponseData) =
        HitchwikiApi(defaultHttpClient(MockEngine(MockEngineConfig().apply {
            addHandler(handler); dispatcher = Dispatchers.Unconfined
        })), "https://example.test")

    @Test fun authTokenPostsCodeAndParsesResponse() = runTest {
        val a = api { req ->
            assertTrue(req.url.encodedPath.endsWith("/api/auth/token"))
            assertEquals(HttpMethod.Post, req.method)
            respond("""{"token":"tok123","username":"alice"}""", HttpStatusCode.OK,
                headersOf(HttpHeaders.ContentType, "application/json"))
        }
        val out = a.authToken("code-abc")
        assertEquals("tok123", out.token)
        assertEquals("alice", out.username)
    }

    @Test fun authMeSendsBearerAndParsesUsername() = runTest {
        val a = api { req ->
            assertTrue(req.url.encodedPath.endsWith("/api/auth/me"))
            assertEquals("Bearer tok123", req.headers[HttpHeaders.Authorization])
            respond("""{"username":"bob"}""", HttpStatusCode.OK,
                headersOf(HttpHeaders.ContentType, "application/json"))
        }
        assertEquals("bob", a.authMe("tok123").username)
    }

    @Test fun authLogoutSendsBearer() = runTest {
        var seen: String? = null
        val a = api { req ->
            seen = req.headers[HttpHeaders.Authorization]
            respond("""{"status":"ok"}""", HttpStatusCode.OK,
                headersOf(HttpHeaders.ContentType, "application/json"))
        }
        a.authLogout("tok123")
        assertEquals("Bearer tok123", seen)
    }
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest --tests "*HitchwikiApiAuthTest"`
Expected: FAIL to compile — `authToken`/`authMe`/`authLogout` unresolved.

- [ ] **Step 3: Create the DTOs**

Create `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/model/AuthDtos.kt`:
```kotlin
package org.hitchwiki.maps.model
import kotlinx.serialization.Serializable

@Serializable
data class TokenRequest(val code: String)

@Serializable
data class TokenResponse(val token: String, val username: String)

@Serializable
data class MeResponse(val username: String)
```

- [ ] **Step 4: Add the API methods**

In `HitchwikiApi.kt`, add the imports:
```kotlin
import io.ktor.client.request.header
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.contentType
import org.hitchwiki.maps.model.MeResponse
import org.hitchwiki.maps.model.TokenRequest
import org.hitchwiki.maps.model.TokenResponse
```
and the methods inside the class (after `recentRides()`):
```kotlin
    suspend fun authToken(code: String): TokenResponse =
        client.post("$baseUrl/api/auth/token") {
            contentType(ContentType.Application.Json)
            setBody(TokenRequest(code))
        }.body()

    suspend fun authMe(token: String): MeResponse =
        client.get("$baseUrl/api/auth/me") {
            header(HttpHeaders.Authorization, "Bearer $token")
        }.body()

    suspend fun authLogout(token: String) {
        client.post("$baseUrl/api/auth/logout") {
            header(HttpHeaders.Authorization, "Bearer $token")
        }
    }
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest --tests "*HitchwikiApiAuthTest"`
Expected: PASS (all three).

- [ ] **Step 6: Commit**

```bash
git add mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/model/AuthDtos.kt \
        mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/data/HitchwikiApi.kt \
        mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/data/HitchwikiApiAuthTest.kt
git commit -m "feat(mobile): HitchwikiApi auth endpoints (token/me/logout) + DTOs"
```

---

### Task 7: Auth seams + `AuthRepository`

The core orchestration, fully unit-tested over fakes. Defines the `TokenStore` and `AuthController` interfaces (Android implements them in Task 9) and the result/status types.

**Files:**
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/data/TokenStore.kt`
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/auth/AuthController.kt`
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/data/AuthRepository.kt`
- Test: `mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/data/AuthRepositoryTest.kt`

**Interfaces:**
- Consumes: `HitchwikiApi.authToken/authMe/authLogout` (Task 6).
- Produces:
  - `interface TokenStore { suspend fun save(token: String); suspend fun load(): String?; suspend fun clear() }`
  - `interface AuthController { suspend fun signIn(): AuthResult }` with `sealed interface AuthResult { data class Success(val code: String); data object Cancelled; data class Error(val message: String) }`
  - `sealed interface AuthStatus { data class SignedIn(val username: String); data object SignedOut; data object Unknown }`
  - `sealed interface SignInOutcome { data class Success(val username: String); data object Cancelled; data class Failed(val message: String) }`
  - `class AuthRepository(controller, store, api)` with `suspend fun signIn(): SignInOutcome`, `suspend fun currentUser(): AuthStatus`, `suspend fun logout()`.

- [ ] **Step 1: Write the failing tests**

Create `mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/data/AuthRepositoryTest.kt`:
```kotlin
package org.hitchwiki.maps.data
import org.hitchwiki.maps.auth.AuthController
import org.hitchwiki.maps.auth.AuthResult
import io.ktor.client.engine.mock.*
import io.ktor.http.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.*
import kotlin.test.*

class AuthRepositoryTest {
    private class FakeStore(var token: String? = null) : TokenStore {
        override suspend fun save(token: String) { this.token = token }
        override suspend fun load(): String? = token
        override suspend fun clear() { token = null }
    }
    private class FakeController(val result: AuthResult) : AuthController {
        override suspend fun signIn(): AuthResult = result
    }
    private fun api(handler: MockRequestHandleScope.(io.ktor.client.request.HttpRequestData) -> HttpResponseData) =
        HitchwikiApi(defaultHttpClient(MockEngine(MockEngineConfig().apply {
            addHandler(handler); dispatcher = Dispatchers.Unconfined
        })), "https://example.test")

    @Test fun signInSuccessStoresTokenAndReturnsUsername() = runTest {
        val store = FakeStore()
        val repo = AuthRepository(FakeController(AuthResult.Success("code1")), store,
            api { respond("""{"token":"T","username":"alice"}""", HttpStatusCode.OK,
                headersOf(HttpHeaders.ContentType, "application/json")) })
        val out = repo.signIn()
        assertEquals(SignInOutcome.Success("alice"), out)
        assertEquals("T", store.token)
    }

    @Test fun signInCancelledStoresNothing() = runTest {
        val store = FakeStore()
        val repo = AuthRepository(FakeController(AuthResult.Cancelled), store,
            api { respond("", HttpStatusCode.OK) })
        assertEquals(SignInOutcome.Cancelled, repo.signIn())
        assertNull(store.token)
    }

    @Test fun currentUserSignedInWhenTokenValid() = runTest {
        val repo = AuthRepository(FakeController(AuthResult.Cancelled), FakeStore("T"),
            api { respond("""{"username":"bob"}""", HttpStatusCode.OK,
                headersOf(HttpHeaders.ContentType, "application/json")) })
        assertEquals(AuthStatus.SignedIn("bob"), repo.currentUser())
    }

    @Test fun currentUserSignedOutWhenNoToken() = runTest {
        val repo = AuthRepository(FakeController(AuthResult.Cancelled), FakeStore(null),
            api { respond("", HttpStatusCode.OK) })
        assertEquals(AuthStatus.SignedOut, repo.currentUser())
    }

    @Test fun currentUser401ClearsTokenAndSignsOut() = runTest {
        val store = FakeStore("bad")
        val repo = AuthRepository(FakeController(AuthResult.Cancelled), store,
            api { respond("""{"error":"unauthorized"}""", HttpStatusCode.Unauthorized,
                headersOf(HttpHeaders.ContentType, "application/json")) })
        assertEquals(AuthStatus.SignedOut, repo.currentUser())
        assertNull(store.token)
    }

    @Test fun currentUserNetworkErrorKeepsTokenAndReturnsUnknown() = runTest {
        val store = FakeStore("T")
        val repo = AuthRepository(FakeController(AuthResult.Cancelled), store,
            api { respond("boom", HttpStatusCode.InternalServerError) })
        assertEquals(AuthStatus.Unknown, repo.currentUser())
        assertEquals("T", store.token)   // offline/5xx must NOT log the user out
    }

    @Test fun logoutClearsTokenLocally() = runTest {
        val store = FakeStore("T")
        val repo = AuthRepository(FakeController(AuthResult.Cancelled), store,
            api { respond("""{"status":"ok"}""", HttpStatusCode.OK,
                headersOf(HttpHeaders.ContentType, "application/json")) })
        repo.logout()
        assertNull(store.token)
    }
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest --tests "*AuthRepositoryTest"`
Expected: FAIL to compile — `TokenStore`/`AuthController`/`AuthResult`/`AuthRepository`/`SignInOutcome`/`AuthStatus` unresolved.

- [ ] **Step 3: Create the seams**

Create `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/data/TokenStore.kt`:
```kotlin
package org.hitchwiki.maps.data

/** Secure local storage for the bearer token. Android impl uses EncryptedSharedPreferences;
 *  tests use an in-memory fake. */
interface TokenStore {
    suspend fun save(token: String)
    suspend fun load(): String?
    suspend fun clear()
}
```

Create `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/auth/AuthController.kt`:
```kotlin
package org.hitchwiki.maps.auth

/** Drives the system-browser OAuth leg and returns the one-time code (or cancel/error).
 *  Android impl opens a Custom Tab and awaits the custom-scheme redirect. */
interface AuthController {
    suspend fun signIn(): AuthResult
}

sealed interface AuthResult {
    data class Success(val code: String) : AuthResult
    data object Cancelled : AuthResult
    data class Error(val message: String) : AuthResult
}
```

- [ ] **Step 4: Implement `AuthRepository`**

Create `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/data/AuthRepository.kt`:
```kotlin
package org.hitchwiki.maps.data
import org.hitchwiki.maps.auth.AuthController
import org.hitchwiki.maps.auth.AuthResult
import io.ktor.client.plugins.ClientRequestException
import io.ktor.http.HttpStatusCode

/** Logged-in identity as far as the app can tell right now. */
sealed interface AuthStatus {
    data class SignedIn(val username: String) : AuthStatus
    data object SignedOut : AuthStatus
    data object Unknown : AuthStatus     // couldn't verify (offline / server error); keep the token
}

/** Result of an interactive sign-in attempt. */
sealed interface SignInOutcome {
    data class Success(val username: String) : SignInOutcome
    data object Cancelled : SignInOutcome
    data class Failed(val message: String) : SignInOutcome
}

/** Orchestrates auth over the three seams. Pure logic — no platform types. */
class AuthRepository(
    private val controller: AuthController,
    private val store: TokenStore,
    private val api: HitchwikiApi,
) {
    suspend fun signIn(): SignInOutcome =
        when (val r = controller.signIn()) {
            is AuthResult.Cancelled -> SignInOutcome.Cancelled
            is AuthResult.Error -> SignInOutcome.Failed(r.message)
            is AuthResult.Success -> try {
                val resp = api.authToken(r.code)
                store.save(resp.token)
                SignInOutcome.Success(resp.username)
            } catch (e: Throwable) {
                SignInOutcome.Failed(e.message ?: "Sign-in failed")
            }
        }

    /** Validate the stored token. 401 => clear + signed out; other errors => keep token, Unknown. */
    suspend fun currentUser(): AuthStatus {
        val token = store.load() ?: return AuthStatus.SignedOut
        return try {
            AuthStatus.SignedIn(api.authMe(token).username)
        } catch (e: ClientRequestException) {
            if (e.response.status == HttpStatusCode.Unauthorized) {
                store.clear()
                AuthStatus.SignedOut
            } else {
                AuthStatus.Unknown
            }
        } catch (e: Throwable) {
            AuthStatus.Unknown
        }
    }

    /** Best-effort server revoke, then always clear locally. */
    suspend fun logout() {
        val token = store.load()
        if (token != null) {
            try { api.authLogout(token) } catch (_: Throwable) { }
        }
        store.clear()
    }
}
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest --tests "*AuthRepositoryTest"`
Expected: PASS (all seven).

- [ ] **Step 6: Commit**

```bash
git add mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/data/TokenStore.kt \
        mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/auth/AuthController.kt \
        mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/data/AuthRepository.kt \
        mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/data/AuthRepositoryTest.kt
git commit -m "feat(mobile): AuthRepository + TokenStore/AuthController seams"
```

---

### Task 8: `AccountViewModel`

The plain-class view model behind the Account screen.

**Files:**
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/account/AccountUiState.kt`
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/account/AccountViewModel.kt`
- Test: `mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/ui/account/AccountViewModelTest.kt`

**Interfaces:**
- Consumes: `AuthRepository`, `AuthStatus`, `SignInOutcome`.
- Produces: `data class AccountUiState(loading, status: AuthStatus = AuthStatus.Unknown, error: String?)`; `class AccountViewModel(repo, scope, workDispatcher = Dispatchers.Default)` with `fun load()`, `fun signIn()`, `fun logout()`.

Note: `AccountViewModel` needs an `AuthRepository` with fakeable seams. Reuse the same fake pattern as `AuthRepositoryTest` by constructing a real `AuthRepository` over fakes — the view model talks only to `AuthRepository`, so a small `FakeAuthRepository` is cleaner. Since `AuthRepository` is a concrete class, extract nothing; instead the test builds an `AuthRepository` over a fake controller/store/api that yields the desired outcomes.

- [ ] **Step 1: Write the failing tests**

Create `mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/ui/account/AccountViewModelTest.kt`:
```kotlin
package org.hitchwiki.maps.ui.account
import org.hitchwiki.maps.auth.AuthController
import org.hitchwiki.maps.auth.AuthResult
import org.hitchwiki.maps.data.*
import io.ktor.client.engine.mock.*
import io.ktor.http.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.*
import kotlin.test.*

class AccountViewModelTest {
    private class FakeStore(var token: String? = null) : TokenStore {
        override suspend fun save(token: String) { this.token = token }
        override suspend fun load(): String? = token
        override suspend fun clear() { token = null }
    }
    private class FakeController(val result: AuthResult) : AuthController {
        override suspend fun signIn(): AuthResult = result
    }
    private fun api(handler: MockRequestHandleScope.(io.ktor.client.request.HttpRequestData) -> HttpResponseData) =
        HitchwikiApi(defaultHttpClient(MockEngine(MockEngineConfig().apply {
            addHandler(handler); dispatcher = Dispatchers.Unconfined
        })), "https://example.test")

    @Test fun loadReflectsSignedInFromStoredToken() = runTest {
        val repo = AuthRepository(FakeController(AuthResult.Cancelled), FakeStore("T"),
            api { respond("""{"username":"bob"}""", HttpStatusCode.OK,
                headersOf(HttpHeaders.ContentType, "application/json")) })
        val vm = AccountViewModel(repo, this, StandardTestDispatcher(testScheduler))
        vm.load(); advanceUntilIdle()
        assertFalse(vm.state.value.loading)
        assertEquals(AuthStatus.SignedIn("bob"), vm.state.value.status)
    }

    @Test fun signInSuccessFlipsToSignedIn() = runTest {
        val repo = AuthRepository(FakeController(AuthResult.Success("c")), FakeStore(),
            api { respond("""{"token":"T","username":"alice"}""", HttpStatusCode.OK,
                headersOf(HttpHeaders.ContentType, "application/json")) })
        val vm = AccountViewModel(repo, this, StandardTestDispatcher(testScheduler))
        vm.signIn(); advanceUntilIdle()
        assertEquals(AuthStatus.SignedIn("alice"), vm.state.value.status)
        assertNull(vm.state.value.error)
    }

    @Test fun signInCancelledLeavesSignedOutNoError() = runTest {
        val repo = AuthRepository(FakeController(AuthResult.Cancelled), FakeStore(),
            api { respond("", HttpStatusCode.OK) })
        val vm = AccountViewModel(repo, this, StandardTestDispatcher(testScheduler))
        vm.signIn(); advanceUntilIdle()
        assertEquals(AuthStatus.SignedOut, vm.state.value.status)
        assertNull(vm.state.value.error)
        assertFalse(vm.state.value.loading)
    }

    @Test fun logoutFlipsToSignedOut() = runTest {
        val repo = AuthRepository(FakeController(AuthResult.Cancelled), FakeStore("T"),
            api { respond("""{"status":"ok"}""", HttpStatusCode.OK,
                headersOf(HttpHeaders.ContentType, "application/json")) })
        val vm = AccountViewModel(repo, this, StandardTestDispatcher(testScheduler))
        vm.logout(); advanceUntilIdle()
        assertEquals(AuthStatus.SignedOut, vm.state.value.status)
    }
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest --tests "*AccountViewModelTest"`
Expected: FAIL to compile — `AccountViewModel`/`AccountUiState` unresolved.

- [ ] **Step 3: Implement the state**

Create `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/account/AccountUiState.kt`:
```kotlin
package org.hitchwiki.maps.ui.account
import org.hitchwiki.maps.data.AuthStatus

data class AccountUiState(
    val loading: Boolean = false,
    val status: AuthStatus = AuthStatus.Unknown,
    val error: String? = null,
)
```

- [ ] **Step 4: Implement the view model**

Create `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/account/AccountViewModel.kt`:
```kotlin
package org.hitchwiki.maps.ui.account
import org.hitchwiki.maps.data.AuthRepository
import org.hitchwiki.maps.data.AuthStatus
import org.hitchwiki.maps.data.SignInOutcome
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class AccountViewModel(
    private val repo: AuthRepository,
    private val scope: CoroutineScope,
    private val workDispatcher: CoroutineDispatcher = Dispatchers.Default,
) {
    private val _state = MutableStateFlow(AccountUiState())
    val state: StateFlow<AccountUiState> = _state.asStateFlow()

    /** Validate on open. Unknown/offline keeps the last state rather than showing an error. */
    fun load() {
        _state.update { it.copy(loading = true, error = null) }
        scope.launch {
            val status = withContext(workDispatcher) { repo.currentUser() }
            _state.update { it.copy(loading = false, status = status) }
        }
    }

    fun signIn() {
        _state.update { it.copy(loading = true, error = null) }
        scope.launch {
            when (val outcome = withContext(workDispatcher) { repo.signIn() }) {
                is SignInOutcome.Success ->
                    _state.update { it.copy(loading = false, status = AuthStatus.SignedIn(outcome.username)) }
                is SignInOutcome.Cancelled ->
                    _state.update { it.copy(loading = false, status = AuthStatus.SignedOut) }
                is SignInOutcome.Failed ->
                    _state.update { it.copy(loading = false, error = outcome.message) }
            }
        }
    }

    fun logout() {
        _state.update { it.copy(loading = true, error = null) }
        scope.launch {
            withContext(workDispatcher) { repo.logout() }
            _state.update { it.copy(loading = false, status = AuthStatus.SignedOut) }
        }
    }
}
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest --tests "*AccountViewModelTest"`
Expected: PASS (all four).

- [ ] **Step 6: Commit**

```bash
git add mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/account/AccountUiState.kt \
        mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/account/AccountViewModel.kt \
        mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/ui/account/AccountViewModelTest.kt
git commit -m "feat(mobile): AccountViewModel (validate-on-load, sign-in, logout)"
```

---

### Task 9: Android impls — EncryptedTokenStore, AndroidAuthController, redirect Activity

The platform seams. Not unit-tested (Android UI / Keystore); verified on-device in Task 10. Build-only here.

**Files:**
- Modify: `mobile/composeApp/build.gradle.kts` (add androidx.browser + androidx.security-crypto to `androidMain`)
- Create: `mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/data/EncryptedTokenStore.kt`
- Create: `mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/auth/AndroidAuthController.kt`
- Create: `mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/auth/OAuthRedirectActivity.kt`
- Modify: `mobile/composeApp/src/androidMain/AndroidManifest.xml` (register the redirect Activity + intent-filter)

**Interfaces:**
- Consumes: `TokenStore`, `AuthController`, `AuthResult` (Task 7).
- Produces: `class EncryptedTokenStore(context: Context) : TokenStore`; `class AndroidAuthController(activity: Activity, baseUrl: String) : AuthController`; `OAuthRedirectActivity` capturing `hitchwiki-app://oauth-callback?code=` and completing the pending sign-in via `AuthRedirectBus`.

- [ ] **Step 1: Add dependencies**

In `mobile/composeApp/build.gradle.kts`, inside the `androidMain.dependencies { }` block, add:
```kotlin
            implementation("androidx.browser:browser:1.8.0")
            implementation("androidx.security:security-crypto:1.1.0-alpha06")
```
(If `androidMain.dependencies` doesn't exist yet, add it under `sourceSets { androidMain { dependencies { … } } }` following the existing structure in the file.)

- [ ] **Step 2: Build to confirm dependencies resolve**

Run: `cd mobile && ./gradlew :composeApp:assembleDebug`
Expected: BUILD SUCCESSFUL (no code using them yet).

- [ ] **Step 3: Implement `EncryptedTokenStore`**

Create `mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/data/EncryptedTokenStore.kt`:
```kotlin
package org.hitchwiki.maps.data
import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** TokenStore backed by EncryptedSharedPreferences (AES via the Android Keystore). */
class EncryptedTokenStore(context: Context) : TokenStore {
    private val prefs by lazy {
        val key = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        EncryptedSharedPreferences.create(
            context,
            "hitchwiki_auth",
            key,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    override suspend fun save(token: String) = withContext(Dispatchers.IO) {
        prefs.edit().putString(KEY, token).apply()
    }

    override suspend fun load(): String? = withContext(Dispatchers.IO) {
        prefs.getString(KEY, null)
    }

    override suspend fun clear() = withContext(Dispatchers.IO) {
        prefs.edit().remove(KEY).apply()
    }

    private companion object { const val KEY = "bearer_token" }
}
```

- [ ] **Step 4: Implement the redirect bus + Activity**

Create `mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/auth/OAuthRedirectActivity.kt`:
```kotlin
package org.hitchwiki.maps.auth
import android.app.Activity
import android.os.Bundle
import kotlinx.coroutines.CompletableDeferred

/** Process-level rendezvous between the Custom Tab redirect and the suspended signIn(). */
object AuthRedirectBus {
    // Set by AndroidAuthController before opening the tab; completed by OAuthRedirectActivity.
    @Volatile var pending: CompletableDeferred<AuthResult>? = null

    fun deliver(result: AuthResult) {
        pending?.complete(result)
        pending = null
    }
}

/** Captures hitchwiki-app://oauth-callback?code=… , hands the code to the bus, finishes. */
class OAuthRedirectActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val code = intent?.data?.getQueryParameter("code")
        AuthRedirectBus.deliver(
            if (code != null) AuthResult.Success(code) else AuthResult.Error("No code in redirect"),
        )
        finish()
    }
}
```

- [ ] **Step 5: Implement `AndroidAuthController`**

Create `mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/auth/AndroidAuthController.kt`:
```kotlin
package org.hitchwiki.maps.auth
import android.app.Activity
import androidx.browser.customtabs.CustomTabsIntent
import androidx.core.net.toUri
import kotlinx.coroutines.CompletableDeferred

/** Opens /api/auth/login in a Chrome Custom Tab and awaits the custom-scheme redirect.
 *  If the tab is dismissed the app resumes without delivering a code; the Account screen's
 *  next action supersedes the stale deferred (see cancelPending). */
class AndroidAuthController(
    private val activity: Activity,
    private val baseUrl: String,
) : AuthController {
    override suspend fun signIn(): AuthResult {
        // Abandon any previous attempt so a dismissed tab can't leave a dangling deferred.
        AuthRedirectBus.deliver(AuthResult.Cancelled)
        val deferred = CompletableDeferred<AuthResult>()
        AuthRedirectBus.pending = deferred
        CustomTabsIntent.Builder().build().launchUrl(activity, "$baseUrl/api/auth/login".toUri())
        return deferred.await()
    }
}
```

Note: the `AuthRedirectBus.deliver(Cancelled)` at the top completes a leftover deferred from a previously dismissed tab (so the *previous* `signIn()` returns `Cancelled`) before starting a fresh attempt. This is the pragmatic cancel path; robust dismissal detection is verified on-device in Task 10.

- [ ] **Step 6: Register the redirect Activity**

In `mobile/composeApp/src/androidMain/AndroidManifest.xml`, add inside `<application>`:
```xml
        <activity
            android:name="org.hitchwiki.maps.auth.OAuthRedirectActivity"
            android:exported="true"
            android:launchMode="singleTask"
            android:theme="@android:style/Theme.Translucent.NoTitleBar">
            <intent-filter>
                <action android:name="android.intent.action.VIEW" />
                <category android:name="android.intent.category.DEFAULT" />
                <category android:name="android.intent.category.BROWSABLE" />
                <data android:scheme="hitchwiki-app" android:host="oauth-callback" />
            </intent-filter>
        </activity>
```

- [ ] **Step 7: Build**

Run: `cd mobile && ./gradlew :composeApp:assembleDebug`
Expected: BUILD SUCCESSFUL.

- [ ] **Step 8: Commit**

```bash
git add mobile/composeApp/build.gradle.kts \
        mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/data/EncryptedTokenStore.kt \
        mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/auth/AndroidAuthController.kt \
        mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/auth/OAuthRedirectActivity.kt \
        mobile/composeApp/src/androidMain/AndroidManifest.xml
git commit -m "feat(mobile): Android EncryptedTokenStore + Custom Tabs auth controller + redirect activity"
```

---

### Task 10: Account UI + wiring (map icon → Account screen), builds + on-device

The visible surface and graph wiring. Ends the phase, so it runs the single iOS compile guard and the on-device end-to-end check.

**Files:**
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/account/AccountScreen.kt`
- Modify: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/map/MapScreen.kt` (account icon + `onOpenAccount`)
- Modify: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/AppNav.kt` (account route + `authRepository` param)
- Modify: `mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/MainActivity.kt` (build the auth graph)

**Interfaces:**
- Consumes: `AccountViewModel`, `AuthStatus`, `AuthRepository`, `AndroidAuthController`, `EncryptedTokenStore`.
- Produces: `@Composable fun AccountScreen(viewModel, onBack)`; `MapScreen` gains `onOpenAccount: () -> Unit`; `AppNav` gains `authRepository: AuthRepository`.

- [ ] **Step 1: Create `AccountScreen`**

Create `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/account/AccountScreen.kt`:
```kotlin
package org.hitchwiki.maps.ui.account
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import org.hitchwiki.maps.data.AuthStatus

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AccountScreen(viewModel: AccountViewModel, onBack: () -> Unit) {
    val state by viewModel.state.collectAsState()
    LaunchedEffect(Unit) { viewModel.load() }

    Scaffold(topBar = {
        TopAppBar(
            title = { Text("Account") },
            navigationIcon = { TextButton(onClick = onBack) { Text("Back") } },
        )
    }) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            when (val s = state.status) {
                is AuthStatus.SignedIn -> {
                    Text("Signed in as", style = MaterialTheme.typography.labelLarge)
                    Text(s.username, style = MaterialTheme.typography.headlineSmall)
                    Spacer(Modifier.height(24.dp))
                    OutlinedButton(onClick = { viewModel.logout() }, enabled = !state.loading) {
                        Text("Log out")
                    }
                }
                else -> {
                    Text("Sign in to log rides with your Hitchwiki account.",
                        style = MaterialTheme.typography.bodyLarge)
                    Spacer(Modifier.height(24.dp))
                    Button(onClick = { viewModel.signIn() }, enabled = !state.loading) {
                        Text("Sign in with Hitchwiki")
                    }
                }
            }
            state.error?.let {
                Spacer(Modifier.height(16.dp))
                Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium)
            }
            if (state.loading) {
                Spacer(Modifier.height(16.dp))
                CircularProgressIndicator()
            }
        }
    }
}
```

- [ ] **Step 2: Add the account icon + `onOpenAccount` to `MapScreen`**

In `MapScreen.kt`, add the parameter to the signature (after `onOpenSearch`):
```kotlin
    onOpenAccount: () -> Unit,
```
Add a person-glyph icon button to the LEFT of the search field inside the search-pill `Row` (before the search field `Row`), so the pill reads `[person] [🔍 Search…] [sliders]`:
```kotlin
                IconButton(onClick = onOpenAccount, modifier = Modifier.size(48.dp)) {
                    PersonIcon(IconBlue)
                }
```
Add the `PersonIcon` composable next to the existing `MagnifierIcon`/`SlidersIcon` at the bottom of the file:
```kotlin
/** Simple person glyph (head + shoulders) drawn with Canvas — dependency-free, matches the
 *  magnifier/sliders icons. */
@Composable
private fun PersonIcon(tint: Color) {
    Canvas(Modifier.size(22.dp)) {
        val w = size.width
        val h = size.height
        drawCircle(tint, radius = h * 0.17f, center = Offset(w * 0.5f, h * 0.30f))
        // Shoulders: a wide arc approximated by a filled rounded rect band.
        drawArc(
            color = tint,
            startAngle = 180f, sweepAngle = 180f, useCenter = true,
            topLeft = Offset(w * 0.18f, h * 0.52f),
            size = androidx.compose.ui.geometry.Size(w * 0.64f, h * 0.62f),
        )
    }
}
```
(`Offset` and `Color` are already imported in `MapScreen.kt` from Task-era icon work; add `import androidx.compose.ui.geometry.Size` only if you prefer the unqualified name.)

- [ ] **Step 3: Wire the account route in `AppNav`**

In `AppNav.kt`, add imports:
```kotlin
import org.hitchwiki.maps.data.AuthRepository
import org.hitchwiki.maps.ui.account.AccountScreen
import org.hitchwiki.maps.ui.account.AccountViewModel
```
Add `authRepository: AuthRepository,` to `AppNav`'s parameters. Pass `onOpenAccount` to the map destination (alongside the existing `onOpenSearch`):
```kotlin
                onOpenAccount = { nav.navigate("account") },
```
Add the destination:
```kotlin
        composable("account") {
            val vm = remember { AccountViewModel(authRepository, scope) }
            AccountScreen(viewModel = vm, onBack = { nav.popBackStack() })
        }
```

- [ ] **Step 4: Build the auth graph in `MainActivity`**

In `MainActivity.kt`, add imports:
```kotlin
import org.hitchwiki.maps.auth.AndroidAuthController
import org.hitchwiki.maps.data.AuthRepository
import org.hitchwiki.maps.data.EncryptedTokenStore
```
After the existing `val recentSource = ApiRecentRidesSource(api)` line, construct:
```kotlin
        val authRepository = AuthRepository(
            controller = AndroidAuthController(this, HitchwikiApi.BASE_URL),
            store = EncryptedTokenStore(applicationContext),
            api = api,
        )
```
(`HitchwikiApi` is already imported via `org.hitchwiki.maps.data.*`.) Then add `authRepository = authRepository,` to the `AppNav(...)` call.

- [ ] **Step 5: Build + iOS compile guard (end of phase)**

Run: `cd mobile && ./gradlew :composeApp:assembleDebug :composeApp:compileKotlinIosSimulatorArm64`
Expected: BUILD SUCCESSFUL. (Single iOS guard for the whole P4 increment — the new auth code is commonMain except the Android impls, so iOS must still compile.)

- [ ] **Step 6: On-device end-to-end check (human)**

Prerequisite: the backend at `HitchwikiApi.BASE_URL` (or a dev backend the app is pointed at) already has P4 endpoints (Tasks 1–5) deployed, and `hitchwiki-app://oauth-callback` need not be registered anywhere but the app.

Install and open the app. Tap the **person icon** in the search bar → the **Account** screen opens showing "Sign in with Hitchwiki". Tap it → a Custom Tab opens the Hitchwiki OAuth page. Approve → the tab redirects back into the app and the Account screen now shows **"Signed in as \<username\>"**. Kill and reopen the app, open Account → it still shows signed-in (token persisted + validated on load). Tap **Log out** → returns to signed-out. Record confirmation.

- [ ] **Step 7: Commit**

```bash
git add mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/account/AccountScreen.kt \
        mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/map/MapScreen.kt \
        mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/AppNav.kt \
        mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/MainActivity.kt
git commit -m "feat(mobile): Account screen + map account icon + auth graph wiring"
```

---

## Self-Review

**Spec coverage:**
- One-time-code flow (durable token never in a URL) → Tasks 2 (code redirect) + 3 (exchange, JSON body). ✓
- Flask-Security built-in token auth, no new token model → Task 3 (`get_auth_token`) + Task 4 (`parse_auth_token`) + Task 5 (`set_uniquifier` revoke). ✓
- Backend `/api/auth/{login,token,me,logout}` additive under `/api/`, web flow untouched → Tasks 2–5 (+ the two-line additive callback branch, guarded by Task 2 Step 7 regression run). ✓
- `AppAuthCode` single-use, short TTL, prod migration noted → Task 1 (+ migration block) + Task 3 (single-use consume + TTL). ✓
- Secure storage behind a seam, Android EncryptedSharedPreferences, iOS unneeded → Task 7 (interface) + Task 9 (impl). ✓
- `AuthController` Custom Tabs + intent-filter redirect → Task 7 (interface) + Task 9 (impl + manifest). ✓
- `AuthRepository` orchestration incl. validate-on-launch, 401-clears, offline-keeps → Task 7 (all covered by tests). ✓
- `AccountViewModel`/`AccountUiState` plain-class pattern → Task 8. ✓
- Account icon → Account screen, AppNav route, MainActivity wiring → Task 10. ✓
- Error/edge handling (cancel, 401, network, reused code) → Task 3 (reuse 400), Task 7 (401/network tests), Task 8 (cancel no-error). ✓
- Testing matrix (backend pytest per endpoint; KMP api/repository/viewmodel) → Tasks 1–8. ✓
- iOS guard once at end → Task 10 Step 5. ✓
- Out of scope (`/ride`, iOS actuals, refresh) → not planned, correct. ✓

**Placeholder scan:** No TBD/TODO; every code step shows full code. The Android UI seams (Task 9) are intentionally build-only with an on-device check (Task 10 Step 6) — documented, not a gap, since EncryptedSharedPreferences/Custom Tabs can't be unit-tested on the JVM.

**Type consistency:** `AuthResult` (`Success(code)`/`Cancelled`/`Error(message)`) is defined in Task 7 and consumed identically in Tasks 7/9. `SignInOutcome` (`Success(username)`/`Cancelled`/`Failed(message)`) and `AuthStatus` (`SignedIn(username)`/`SignedOut`/`Unknown`) defined in Task 7, consumed in Tasks 8/10. `TokenResponse(token, username)`/`MeResponse(username)`/`TokenRequest(code)` defined in Task 6, used by `AuthRepository` (Task 7) and the API (Task 6). Backend: `create_app_auth_code`/`consume_app_auth_code`/`finish_mobile_login`/`user_from_bearer` names are consistent across Tasks 2–5. `AuthRepository(controller, store, api)` constructor order matches every test and the Task-10 wiring. `MapScreen` gains `onOpenSearch` (existing) + `onOpenAccount` (Task 10); `AppNav` gains `recentSource` (existing) + `authRepository` (Task 10).

## Deferred (not in this plan)

`POST /ride` bearer/JSON write + outbox (P5); iOS auth actuals (Keychain + `ASWebAuthenticationSession`); token refresh/expiry policy; multi-device token management; nav drawer.
