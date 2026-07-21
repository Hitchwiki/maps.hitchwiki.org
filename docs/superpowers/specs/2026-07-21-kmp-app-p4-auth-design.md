# KMP App P4 — Auth (mobile OAuth + bearer token) — Design

**Status:** Approved design, ready for implementation planning.

**Phase:** P4 of the KMP app roadmap (`docs/superpowers/specs/2026-07-14-kmp-app-v1-design.md`).
Follows P3 (UI) — map, spot detail, filters/search, recent are shipped on Android.

## Goal

Let a user sign in with their Hitchwiki account from the Android app via the system
browser, receive a **bearer token**, store it securely, validate it on launch, see their
identity, and log out. This establishes the authenticated identity that P5 (ride write) will
require — but P4 does **not** touch `/ride`.

## Scope

**In scope**
- System-browser OAuth (AppAuth pattern) ending in a bearer token, via a **one-time-code
  exchange** (the durable token never travels in a URL).
- Secure local token storage (Android EncryptedSharedPreferences), behind an `expect/actual`
  seam. iOS actual stays a stub.
- Validate-on-launch: a stored token is confirmed against the backend; an invalid token is
  cleared.
- An **Account** surface: an account icon in the map top bar → an Account screen with
  "Sign in with Hitchwiki" (logged out) / username + "Log out" (logged in).
- Additive backend endpoints under `/api/auth/`. The existing web session flow is untouched.

**Out of scope (later phases)**
- `POST /ride` bearer/JSON write path and the outbox → **P5**. P4 only leaves `TokenStore`
  as the seam P5 reads.
- iOS auth actuals (Custom Tabs / Keychain equivalents).
- Multi-account / device management UI, token refresh rotation schedules.

## Key decisions

| Decision | Choice | Why |
|---|---|---|
| Backend token | **Flask-Security built-in token auth** | `User` uses `FsUserMixin` → `fs_uniquifier` already present. `user.get_auth_token()` signs a token with no new model; logout revokes by rotating `fs_uniquifier`. Least new Python. |
| Redirect security | **One-time-code exchange** (not token-in-URL) | AppAuth-standard shape. The callback redirects with a short-lived single-use `code`; the app exchanges it for the bearer token in a **JSON body**, keeping the durable token out of browser history / redirect chains. |
| Sign-in entry point | **Account icon → Account screen** | Gives P4 a visible, testable surface without a full nav drawer. |
| Token lifetime | **Long-lived until logout** | No expiry configured; logout rotates `fs_uniquifier` server-side and clears local storage. Offline launches keep the last token. |
| iOS | **Stubbed actuals** | Android is the run/ship target; shared code keeps compiling. |

## Auth flow (approach B — one-time-code)

```
App (Account screen: "Sign in")
  │  AuthController.signIn()  → open Chrome Custom Tab
  ▼
System browser → GET /api/auth/login
  │  marks session["oauth_mobile"] = True, then the EXISTING Hitchwiki authorize redirect
  ▼
Hitchwiki OAuth2 authorize → user approves
  ▼
GET /login?code=<hw_code>&state=…   (the shared existing callback, _handle_callback)
  │  existing exchange: token → profile → find/create local User
  │  mobile flag set → mint single-use AppAuthCode(code → user, short TTL), then:
  ▼
302 → hitchwiki-app://oauth-callback?code=<app_code>
  │  Android intent-filter Activity captures it, resumes the suspended signIn()
  ▼
App → POST /api/auth/token  { code: <app_code> }
  ◀  200 { token: user.get_auth_token(), username }
  │  store token in EncryptedSharedPreferences
  ▼
Logged in. Later: Authorization: Bearer <token> on /api/auth/me, /api/auth/logout, (P5) /ride
```

Cancellation: dismissing the Custom Tab resumes `signIn()` as cancelled (no error).

## Backend (all additive, under `/api/auth/`, web session flow unchanged)

New blueprint `hitch/blueprints/api_auth.py`, registered alongside the others. Reuses the
`oauth` blueprint's helpers where possible.

- **`GET /api/auth/login`** — mirrors `oauth.login_oauth`: generates `state` and stores it in
  `session["oauth_state"]` (exactly as `login_oauth` does, so the shared callback's CSRF check
  passes), additionally sets `session["oauth_mobile"] = True`, then redirects to the same
  Hitchwiki authorize URL with the same `_redirect_uri()`. (So the callback still lands on the
  existing `/login?code=` route.)

- **Shared callback change (`hitch/blueprints/oauth.py`, `_handle_callback`)** — after the
  existing token/profile/find-or-create-user logic, branch on `session.pop("oauth_mobile",
  False)`:
  - Web (unchanged): `login_user(...)` + `_finish_login(...)`.
  - Mobile: create an `AppAuthCode` row (`code` = `secrets.token_urlsafe(32)`, `user_id`,
    `created_at`; single-use, ~5 min TTL) and `redirect("hitchwiki-app://oauth-callback?code="
    + code)`. No session cookie needed for the mobile client.

- **`POST /api/auth/token`** — body `{code}`. Look up an unconsumed, unexpired `AppAuthCode`;
  delete/mark it consumed (single-use); return `{ "token": user.get_auth_token(), "username":
  user.username }`. Unknown/expired/reused code → 400.

- **`GET /api/auth/me`** — reads `Authorization: Bearer <token>`, verifies it via
  Flask-Security's token verifier (a small helper, since FS's default token header is
  `Authentication-Token`, not `Authorization`), returns `{ "username": user.username }` or 401.

- **`POST /api/auth/logout`** — Bearer → rotate the user's `fs_uniquifier` (invalidates the
  token server-side) → 200. Client also clears local storage regardless.

**New model:** `AppAuthCode(id, code UNIQUE, user_id FK, created_at)` in `hitch/models.py`.
Single-use bridge only; not the durable credential. Needs the manual prod migration
(`ALTER TABLE`/`create_all`) per CLAUDE.md's "Database migrations" note.

**Config:** the custom scheme (`hitchwiki-app`) and callback are backend constants;
`HITCHWIKI_OAUTH_REDIRECT_*` are unchanged (the mobile redirect to the app is separate from
the Hitchwiki `redirect_uri`, which stays the backend URL).

## KMP components

All commonMain unless noted; `expect/actual` only where the platform is unavoidable.

- **`TokenStore`** (`data/`, `expect`) — `suspend save(token)`, `suspend load(): String?`,
  `suspend clear()`. Android actual: EncryptedSharedPreferences (androidx.security.crypto).
  iOS actual: stub (`TODO`).

- **`AuthController`** (`auth/`, `expect`) — `suspend fun signIn(): AuthResult` where
  `AuthResult = Success(code) | Cancelled | Error(message)`. Android actual: launches a Chrome
  Custom Tab to `<baseUrl>/api/auth/login` and suspends a `CompletableDeferred` until the
  redirect Activity delivers `?code=` (or the tab is dismissed → `Cancelled`). iOS actual:
  stub.

- **`AuthRepository`** (`data/`) — orchestrates, pure over the seams:
  - `signIn()`: `AuthController.signIn()` → on `Success(code)` → `api.authToken(code)` → store
    token → return the username.
  - `currentUser()`: `load()` token → `api.authMe(token)` → username; on 401 → `clear()` →
    null (logged out); on network error → keep token, signal "unknown/offline".
  - `logout()`: `api.authLogout(token)` (best-effort) → `clear()`.

- **`AccountViewModel` / `AccountUiState`** (`ui/account/`) — plain-class VM (constructor takes
  `AuthRepository`, `CoroutineScope`, injected `workDispatcher`). State
  `{ loading, username: String?, signedIn: Boolean, error: String? }`; `load()` (validate on
  open), `signIn()`, `logout()`.

- **`HitchwikiApi`** — add `authToken(code): TokenResponse`, `authMe(token): MeResponse`,
  `authLogout(token)`. New `@Serializable` DTOs `TokenResponse(token, username)` and
  `MeResponse(username)`.

## UI

- **Account icon** — a person glyph drawn with Canvas (same dependency-free approach as the
  P3 sliders/magnifier icons), placed in the map top bar (leading the search pill). A subtle
  filled state (or no change) is fine; identity detail lives on the Account screen.
- **`AccountScreen`** — logged out: title + "Sign in with Hitchwiki" button (→
  `viewModel.signIn()`); logged in: the username + "Log out" (→ `viewModel.logout()`); a
  spinner while `loading`, an inline error line on failure.
- **Wiring** — new `account` route in `AppNav`; `MapScreen` gains `onOpenAccount`;
  `MainActivity` constructs `AuthController` + `TokenStore` + `AuthRepository` and passes them
  in. `MapViewModel` is unaffected.

## Error / edge handling

- Custom Tab dismissed before completing → `Cancelled` → return to Account screen quietly.
- `/api/auth/me` **401** → token invalid/revoked → clear store → logged-out state.
- `/api/auth/me` **network failure** → keep the token; show last-known username if any, else a
  neutral "couldn't verify" — never force logout while offline.
- `/api/auth/token` failure (bad/expired/reused code) → Account-screen error; no token stored.
- Reused `AppAuthCode` → 400 (single-use), so a replayed redirect can't mint a second token.

## Testing

- **Backend (pytest, `tests/`):**
  - `/api/auth/login` sets `oauth_mobile` and 302s to the Hitchwiki authorize URL.
  - Mobile callback creates an `AppAuthCode` and 302s to `hitchwiki-app://oauth-callback?code=`
    (web callback path unchanged — existing tests still pass).
  - `/api/auth/token` exchanges a code once, returns a working token, and rejects a reused or
    expired code with 400.
  - `/api/auth/me` returns the username for a valid Bearer token and 401 for a bad one.
  - `/api/auth/logout` rotates `fs_uniquifier` so the previous token then 401s on `/me`.

- **KMP (`commonTest`, MockEngine + fakes):**
  - `AuthRepository.signIn()` happy path: fake `AuthController` yields a code → `/api/auth/token`
    → token stored → username returned.
  - `currentUser()`: stored token + `/me` 200 → logged in; `/me` 401 → store cleared, logged
    out; `/me` network error → token retained.
  - Cancel path: `AuthController` returns `Cancelled` → no store write, no error state.
  - `AccountViewModel`: `load()` reflects signed-in vs signed-out; `logout()` clears and flips
    state.

## Deferred (not in this plan)

`POST /ride` bearer/JSON write + outbox (P5); iOS auth actuals; token refresh/expiry policy;
multi-device token management; any nav drawer.
