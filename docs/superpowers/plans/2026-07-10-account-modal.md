# Account Modal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Open the account UI (logged-out login pitch, or username + insights + recent rides) in a modal so the map page never unloads. Issue #106.

**Architecture:** A new `GET /me.json` serves the modal's data; an opt-in `?popup=1` variant of the OAuth flow lets login complete in a popup that `postMessage`s the opener; `account.js` renders the modal and intercepts the avatar click.

**Design doc:** `docs/superpowers/specs/2026-07-10-account-modal-design.md`

## Global Constraints

- `/me.json` returns `200 {"logged_in": false}` for anonymous callers — never a 302 to `/login`.
- `/me.json` sets `Cache-Control: private, no-store` and must never be `public`.
- `rides` in `/me.json` is capped at `RIDES_IN_MODAL_CAP = 50`; `rides_total` is the untruncated count.
- Ride entries omit the internal `submission_sort_key`.
- The popup postMessage targets `window.location.origin` explicitly, never `"*"`. The opener validates `event.origin === window.location.origin` and `event.source === popupHandle`.
- The non-popup OAuth flow is unchanged: callback still 302s to `/me` (existing user) or `/edit-user` (new user).
- The account modal must NOT use `journeyUI._openDialog` (its single-flight guard tears down parent sheets).
- The avatar stays an `<a href="/me">`; JS calls `preventDefault()`. Middle-click / no-JS still navigate.

---

### Task 1: `GET /me.json`

**Files:**
- Modify: `hitch/blueprints/user.py`
- Test: `tests/test_me_json.py` (create)

**Interfaces:**
- Produces: `GET /me.json` → the payload in the design doc. Reuses `_distinct_partner_count(username)` and `_get_rides_for_user(user)`.

- [ ] **Step 1: Write the failing tests** (`tests/test_me_json.py`)

```python
def test_me_json_anonymous_is_200_and_logged_out(client):
    resp = client.get("/me.json")
    assert resp.status_code == 200          # never a 302 to /login
    assert resp.get_json() == {"logged_in": False}


def test_me_json_is_never_publicly_cacheable(client):
    resp = client.get("/me.json")
    cc = resp.headers.get("Cache-Control", "")
    assert "public" not in cc
    assert "no-store" in cc


def test_me_json_logged_in_payload(client, logged_in_user):
    resp = client.get("/me.json")
    body = resp.get_json()
    assert body["logged_in"] is True
    assert body["username"] == logged_in_user.username
    assert body["profile_url"] == "/me"
    assert set(body["insights"]) == {"rides", "distance_km", "waiting_min", "partners"}
    assert isinstance(body["rides"], list)
    assert body["rides_total"] >= len(body["rides"])
    assert len(body["rides"]) <= 50
    for r in body["rides"]:
        assert "submission_sort_key" not in r
```

Add a `logged_in_user` fixture to `tests/conftest.py` that creates a `User` and sets `session["_user_id"]` via `client.session_transaction()` (login is OAuth, so there is no form to post).

- [ ] **Step 2: Run to verify failure** — `.venv/bin/python -m pytest tests/test_me_json.py -v` → 404 / fixture error.

- [ ] **Step 3: Implement** in `hitch/blueprints/user.py`:

```python
RIDES_IN_MODAL_CAP = 50


@user_bp.route("/me.json", methods=["GET"])
def me_json():
    """Account data for the on-map modal (issue #106).

    Anonymous callers get 200 {"logged_in": false} rather than a redirect to /login:
    the modal renders its logged-out state from this response and must never follow a 302.
    """
    if current_user.is_anonymous:
        resp = jsonify({"logged_in": False})
    else:
        rides = _get_rides_for_user(current_user)
        shown = [{k: v for k, v in r.items() if k != "submission_sort_key"} for r in rides[:RIDES_IN_MODAL_CAP]]
        resp = jsonify({
            "logged_in": True,
            "username": current_user.username,
            "needs_profile": not bool(current_user.hitchwiki_username),
            "profile_url": "/me",
            "insights": {
                "rides": current_user.total_rides or 0,
                "distance_km": current_user.total_distance_km or 0,
                "waiting_min": current_user.total_waiting_time_min or 0,
                "partners": _distinct_partner_count(current_user.username),
            },
            "rides": shown,
            "rides_total": len(rides),
        })
    # Per-user data: never let a shared cache store or reuse it (see PR #105).
    resp.headers["Cache-Control"] = "private, no-store"
    return resp
```

- [ ] **Step 4: Verify pass**, then `.venv/bin/ruff check hitch/ tests/`.

- [ ] **Step 5: Commit** — `feat(account): serve /me.json for the on-map account modal`

---

### Task 2: OAuth popup completion

**Files:**
- Modify: `hitch/blueprints/oauth.py`
- Create: `hitch/templates/security/oauth_popup_done.html`
- Test: `tests/test_oauth_popup.py` (create)

**Interfaces:**
- Consumes: `/login/oauth?popup=1`.
- Produces: callback renders `oauth_popup_done.html` (200) when `session["oauth_popup"]`, else the existing 302.

- [ ] **Step 1: Write the failing tests**

```python
def test_popup_flag_is_set_and_state_still_stored(client):
    resp = client.get("/login/oauth?popup=1")
    assert resp.status_code == 302          # still redirects to Hitchwiki
    with client.session_transaction() as sess:
        assert sess["oauth_popup"] is True
        assert sess["oauth_state"]


def test_plain_login_oauth_sets_no_popup_flag(client):
    client.get("/login/oauth")
    with client.session_transaction() as sess:
        assert "oauth_popup" not in sess
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement.** In `login_oauth`, before redirecting:

```python
    # The Hitchwiki redirect back carries only `code` and `state`, so remember here
    # that the flow began in a popup; the callback needs it to close the popup
    # instead of navigating the (hidden) window to /me.
    if request.args.get("popup"):
        session["oauth_popup"] = True
    else:
        session.pop("oauth_popup", None)
```

In `_handle_callback`, replace each terminal `redirect(...)` with a helper:

```python
def _finish_login(target, needs_profile):
    """End the OAuth flow: close the popup, or redirect a full-page flow as before."""
    if session.pop("oauth_popup", False):
        return render_template("security/oauth_popup_done.html", needs_profile=needs_profile)
    return redirect(target)
```

`oauth_popup_done.html` posts to the opener at our own origin and closes:

```html
<script>
  (function () {
    var msg = { type: "hitchwiki-auth", ok: true, needsProfile: {{ needs_profile|tojson }} };
    // Same-origin by construction: target our own origin explicitly, never "*".
    if (window.opener) window.opener.postMessage(msg, window.location.origin);
    window.close();
  })();
</script>
<p>Signed in. You can close this window.</p>
```

- [ ] **Step 4: Verify pass + ruff.**
- [ ] **Step 5: Commit** — `feat(oauth): allow the login flow to complete in a popup`

---

### Task 3: The modal

**Files:**
- Create: `hitch/static/account.js`
- Modify: `hitch/templates/map.html` (load the script), `hitch/static/style.css`
- Test: `tests/account.test.js` (create)

**Interfaces:**
- Consumes: `GET /me.json`, `/login/oauth?popup=1`.
- Produces: `window.AccountModal.open()`; pure helpers `formatInsights(insights)` and `ridesSummary(shown, total)` exported for node.

- [ ] **Step 1: Write the failing node tests** (`tests/account.test.js`) for the pure helpers:

```js
const A = require("../hitch/static/account.js");
test("ridesSummary reports truncation", () => {
  assert.strictEqual(A.ridesSummary(50, 231), "Showing 50 of 231 rides");
  assert.strictEqual(A.ridesSummary(3, 3), "3 rides");
});
test("formatInsights rounds distance and formats waiting time", () => {
  const s = A.formatInsights({ rides: 42, distance_km: 5312.44, waiting_min: 980, partners: 7 });
  assert.strictEqual(s.distance, "5,312 km");
  assert.strictEqual(s.waiting, "16 h 20 m");
});
```

- [ ] **Step 2: Run to verify failure** — `node --test tests/account.test.js`.

- [ ] **Step 3: Implement `account.js`.** Dual export (browser `window.AccountModal` + CommonJS) like `ride_submit.js`. Must include:
  - `open()` → build scrim + sheet, `L.DomEvent.disableClickPropagation` on the sheet, fetch `/me.json`, render.
  - Logged-out render: pitch + "Log in with Hitchwiki" button → `startLogin()`.
  - `startLogin()`:
    ```js
    const popup = window.open("/login/oauth?popup=1", "hitchwiki-login", "width=520,height=640");
    if (!popup) { window.location.href = "/login/oauth"; return; }   // popup blocked (mobile Safari)
    function onMsg(e) {
      // Only trust a message from OUR origin, sent by the popup we opened.
      if (e.origin !== window.location.origin || e.source !== popup) return;
      if (!e.data || e.data.type !== "hitchwiki-auth") return;
      window.removeEventListener("message", onMsg);
      refresh(e.data.needsProfile);
    }
    window.addEventListener("message", onMsg);
    ```
  - Logged-in render: username, insight summary, first 10 rides, a "Show all" button revealing the rest, `needs_profile` → "Finish setting up your profile" link to `/edit-user`, and "View full profile" → `profile_url`.
  - Own scrim + Escape/scrim dismissal. Do **not** touch `journeyUI._openDialog`.

- [ ] **Step 4: Wire the avatar** in `hitch/templates/map.html` — keep `<a href="/me">`, add `id`, and in `account.js`:
  ```js
  link.addEventListener("click", function (e) {
    if (e.metaKey || e.ctrlKey || e.button === 1) return;  // let new-tab through
    e.preventDefault();
    AccountModal.open();
  });
  ```
  Load `<script src="{{ asset_url('/static/account.js') }}"></script>` (asset_url gives the `?v=` buster that PR #105's immutable caching keys on).

- [ ] **Step 5: Style** `.acct-*` classes in `style.css`, matching the in-ride sheet.

- [ ] **Step 6: Verify** — `node --test tests/*.test.js`, `node --check hitch/static/account.js`, full pytest, ruff.

- [ ] **Step 7: Commit** — `feat(account): open login + profile in an on-map modal`

---

## Self-Review

- **Spec coverage:** `/me.json` + anon 200 + cache header + ride cap (Task 1); popup flag, postMessage page, unchanged full-page flow (Task 2); modal render, popup-blocked fallback, origin+source validation, avatar interception, no `_openDialog` (Task 3).
- **Placeholders:** none.
- **Type consistency:** `needs_profile` (JSON, snake) ↔ `needsProfile` (postMessage, camel) is deliberate and stated in both tasks; `RIDES_IN_MODAL_CAP = 50` used in Task 1 and asserted in its test.
