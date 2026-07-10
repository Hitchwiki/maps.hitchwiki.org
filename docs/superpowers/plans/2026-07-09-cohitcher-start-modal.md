# Co-hitcher Start-of-Journey Modal — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a hitchhiker record who else is hitching with them at journey start, via an optional modal that reuses the existing username-autocomplete and the existing `CoHitchhiker` submit path.

**Architecture:** Frontend-only feature plus one backend touch (`window.USERNAME`). Co-hitchers are collected in a modal shown before a journey is seeded, stored on the localStorage journey object (`j.coHitchhikers`), and submitted with the ride's existing `co_hitchhiker` form field at Finish AND Give Up. `/ride` already writes `CoHitchhiker` rows from that field, so there is no new backend write logic.

**Tech Stack:** Vanilla JS (`inride.js` IIFE + `ride_submit.js` dual-export module, `node --test`), Flask/Jinja, pytest.

**Design spec:** `docs/superpowers/specs/2026-07-09-cohitcher-start-modal-design.md`

## Global Constraints

- **No new backend write logic.** `/ride` already processes `co_hitchhiker` (comma-separated usernames) and writes `CoHitchhiker` rows keyed by `d_tag` (`hitch/blueprints/main.py:699`); the in-ride submit path already reaches it. Only *feed* that field from the in-ride flow.
- **Reuse the existing username autocomplete:** `GET /search_usernames?q=<query>` → JSON array of username strings.
- **`co_hitchhiker`** is submitted as a comma-separated username string.
- **Exclude self and de-dupe:** a logged-in user cannot add their own username (`window.USERNAME`); duplicates are ignored.
- **Optional, no Skip:** the field is optional; a single always-enabled "Start hitching" button begins the journey. Dismissing the modal (scrim/×) **aborts** the start — no journey begins.
- **Show the modal on every NEW-journey start**, not on resume of an already-started journey. The three new-start sites are `startFromChoose` logged-in branch, "Continue anonymously", and the post-login-redirect resume.
- **`window.USERNAME`** is exposed via Jinja `tojson` (safe JS string literal).
- Python: `ruff` line length 130. JS: verify with `node --check`; DOM code with no unit-test surface is verified on-device.

---

## File Structure

- `hitch/blueprints/main.py` — **modify.** Pass `username` into the `render_map` template context.
- `hitch/templates/map.html` — **modify.** Emit `window.USERNAME`.
- `hitch/static/ride_submit.js` — **modify.** Add `co_hitchhiker` to `buildFinishBody`; add pure `buildGiveUpBody`.
- `hitch/static/inride.js` — **modify.** Use `buildGiveUpBody`; `start()` stores `coHitchhikers`; add `coHitcherSheet` + `beginWithCoHitchers`; route the three new-start sites through it.
- `hitch/static/style.css` — **modify.** Modal chip + suggestion-dropdown styles.
- Tests: `tests/ride_submit.test.js` (extend), `tests/test_window_username.py` (new).

---

### Task 1: Expose `window.USERNAME`

**Files:**
- Modify: `hitch/blueprints/main.py` (the `render_map` view, ~line 89-95)
- Modify: `hitch/templates/map.html:43`
- Test: `tests/test_window_username.py`

**Interfaces:**
- Produces: `window.USERNAME` — the logged-in user's username, or `""` when anonymous.

- [ ] **Step 1: Write the failing test**

Create `tests/test_window_username.py`:

```python
# Anonymous visitors must still get a defined (empty) window.USERNAME so the
# co-hitcher modal's JS can read it unconditionally.
def test_window_username_empty_for_anonymous(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b'window.USERNAME = "";' in resp.data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_window_username.py -v`
Expected: FAIL — `window.USERNAME` not in the response.

- [ ] **Step 3: Pass `username` into the template context**

In `hitch/blueprints/main.py`, in the `render_map` view, add a `username` kwarg to the `render_template(...)` call that already passes `is_logged_in=not current_user.is_anonymous`:

```python
        username=("" if current_user.is_anonymous else current_user.username),
```

- [ ] **Step 4: Emit it in the template**

In `hitch/templates/map.html`, immediately after line 43 (`<script>window.IS_LOGGED_IN = ...;</script>`), add:

```html
<script>window.USERNAME = {{ (username or '')|tojson }};</script>
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_window_username.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add hitch/blueprints/main.py hitch/templates/map.html tests/test_window_username.py
git commit -m "feat(map): expose window.USERNAME for the co-hitcher modal"
```

---

### Task 2: Carry `co_hitchhiker` through the submit bodies

**Files:**
- Modify: `hitch/static/ride_submit.js`
- Modify: `hitch/static/inride.js` (the `journeyFlow.giveUp` inline body → use `buildGiveUpBody`)
- Test: `tests/ride_submit.test.js` (extend)

**Interfaces:**
- Consumes: a journey `j` that may carry `j.coHitchhikers` (array of usernames).
- Produces: `RideSubmit.buildFinishBody(...)` now includes `co_hitchhiker`; new `RideSubmit.buildGiveUpBody(j, waitMin, details, id) -> body` (pure) including `co_hitchhiker`.

- [ ] **Step 1: Write the failing tests**

In `tests/ride_submit.test.js`, add:

```js
test("buildFinishBody carries co_hitchhiker as CSV", () => {
  const j = {
    pickup: { lat: 1, lon: 2 }, gotRideMs: Date.now(), finalWaitMs: 0,
    coHitchhikers: ["sam", "jo"], details: { rating: 4 },
  };
  const body = RideSubmit.buildFinishBody(j, { lat: 3, lon: 4 }, Date.now(), "id1");
  assert.strictEqual(body.co_hitchhiker, "sam,jo");
});

test("buildFinishBody co_hitchhiker is empty string when none", () => {
  const j = { pickup: { lat: 1, lon: 2 }, gotRideMs: Date.now(), finalWaitMs: 0, details: { rating: 4 } };
  const body = RideSubmit.buildFinishBody(j, { lat: 3, lon: 4 }, Date.now(), "id1");
  assert.strictEqual(body.co_hitchhiker, "");
});

test("buildGiveUpBody builds a destination-less body with co_hitchhiker", () => {
  const j = { pickup: { lat: 5, lon: 6 }, coHitchhikers: ["sam"] };
  const body = RideSubmit.buildGiveUpBody(j, 12, { rating: 3, comment: "cold" }, "gid");
  assert.strictEqual(body.rate, "3");
  assert.strictEqual(body.wait, "12");
  assert.strictEqual(body.comment, "cold");
  assert.strictEqual(body.signal, "");
  assert.strictEqual(body.vehicle_kind, "");
  assert.strictEqual(body.co_hitchhiker, "sam");
  assert.strictEqual(body.pickup_lat, 5);
  assert.strictEqual(body.destination_lat, "");
  assert.strictEqual(body.client_d_tag, "gid");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test tests/ride_submit.test.js`
Expected: FAIL — `body.co_hitchhiker` is undefined; `RideSubmit.buildGiveUpBody` is not a function.

- [ ] **Step 3: Add `co_hitchhiker` to `buildFinishBody` and add `buildGiveUpBody`**

In `hitch/static/ride_submit.js`, inside `buildFinishBody`'s returned object, add this line (next to the other demographic fields):

```js
      co_hitchhiker: (j.coHitchhikers || []).join(","),
```

Then add a new function next to `buildFinishBody` and include it in the returned module object:

```js
  // Destination-less give-up body (rated wait, no ride). Pure so it is unit-testable;
  // co-hitchers who waited together are attached here too.
  function buildGiveUpBody(j, waitMin, details, id) {
    return {
      rate: String(details.rating || ""),
      wait: String(waitMin),
      comment: details.comment || "",
      signal: "", vehicle_kind: "",
      co_hitchhiker: (j.coHitchhikers || []).join(","),
      pickup_lat: j.pickup.lat, pickup_lon: j.pickup.lon,
      destination_lat: "", destination_lon: "",
      client_d_tag: id,
    };
  }
```

Update the module's return to include it:

```js
  return { isoLocal, buildFinishBody, buildGiveUpBody };
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test tests/ride_submit.test.js`
Expected: PASS (all prior + 3 new).

- [ ] **Step 5: Wire `journeyFlow.giveUp` to use `buildGiveUpBody`**

In `hitch/static/inride.js`, in `journeyFlow.giveUp`, replace the inline `body: { ... }` object with a call to the shared builder. The block currently reads:

```js
      outboxStore.add({
        id: id, kind: "giveup", createdAt: Date.now(), attempts: 0, lastError: null, status: "pending",
        body: {
          rate: String(details.rating || ""),
          wait: String(waitMin),
          comment: details.comment || "",
          signal: "", vehicle_kind: "",
          pickup_lat: j.pickup.lat, pickup_lon: j.pickup.lon,
          destination_lat: "", destination_lon: "",
          client_d_tag: id,
        },
      });
```

Replace it with:

```js
      outboxStore.add({
        id: id, kind: "giveup", createdAt: Date.now(), attempts: 0, lastError: null, status: "pending",
        body: window.RideSubmit.buildGiveUpBody(j, waitMin, details, id),
      });
```

- [ ] **Step 6: Verify inride.js still parses**

Run: `node --check hitch/static/inride.js`
Expected: OK.

- [ ] **Step 7: Commit**

```bash
git add hitch/static/ride_submit.js hitch/static/inride.js tests/ride_submit.test.js
git commit -m "feat(inride): carry co_hitchhiker into Finish and Give Up bodies"
```

---

### Task 3: Co-hitcher modal + start-with-co-hitchers flow

**Files:**
- Modify: `hitch/static/inride.js`
- Modify: `hitch/static/style.css`

**Interfaces:**
- Consumes: `window.USERNAME` (Task 1); `GET /search_usernames?q=`.
- Produces: `journeyFlow.start(latlng, coHitchhikers)` stores `j.coHitchhikers`; `journeyFlow.beginWithCoHitchers(latlng)` shows the modal then starts; `journeyUI.coHitcherSheet(onStart)`.

This task is DOM/browser code with no unit-test surface (matching the rest of `inride.js`); it is verified with `node --check` plus explicit on-device steps at the end.

- [ ] **Step 1: Store `coHitchhikers` on the journey**

In `hitch/static/inride.js`, change `journeyFlow.start` to accept and persist the list. It currently is `journeyFlow.start = function (latlng) {` seeding an object without co-hitchers. Update the signature and add the field:

```js
  journeyFlow.start = function (latlng, coHitchhikers) {
    const j = journeyStore.set({
      state: "waiting",
      pickup: { lat: latlng.lat, lon: latlng.lng },
      coHitchhikers: coHitchhikers || [],
      waitAccumMs: 0,
      waitSegmentStartMs: Date.now(),
      gotRideMs: null,
      finalWaitMs: null,
      details: null,
      legIndex: 0,
    });
    journeyUI.render(j);
  };
```

(Resume-on-load already restores the whole journey object from localStorage, so `coHitchhikers` persists across reloads with no extra work. `journeyFlow.nextRide`/`whatsNext` starts, if any, keep their existing signatures — a new leg carries no fresh co-hitcher prompt.)

- [ ] **Step 2: Add the co-hitcher modal `coHitcherSheet`**

In `hitch/static/inride.js`, add this method to the `journeyUI` object (near the other sheet builders like `giveUpSheet`). It manages its own selected-set and calls `onStart(list)` on confirm:

```js
    // Start-of-journey modal: optional co-hitcher entry (reuses /search_usernames).
    // onStart(coHitchhikers[]) fires on "Start hitching"; dismissing aborts the start.
    coHitcherSheet(onStart) {
      if (journeyUI._openDialog) journeyUI._openDialog.close();
      const selected = [];
      const self = (window.USERNAME || "").toLowerCase();

      const scrim = document.createElement("div");
      scrim.className = "inride-scrim";
      const sheet = document.createElement("div");
      sheet.className = "inr-sheet";

      const grab = document.createElement("div");
      grab.className = "inr-sheet__grab";
      sheet.appendChild(grab);

      const closeX = document.createElement("button");
      closeX.type = "button";
      closeX.className = "inr-sheet__close";
      closeX.setAttribute("aria-label", "Close");
      closeX.innerHTML = "&times;";
      closeX.addEventListener("click", function () { close(); });
      sheet.appendChild(closeX);

      const titleEl = document.createElement("h4");
      titleEl.textContent = window.USERNAME ? "Who else is hitching?" : "Who's hitching with you?";
      sheet.appendChild(titleEl);

      // Logged-in confirmation line ("You're hitching as @name"); omitted when anonymous.
      if (window.USERNAME) {
        const who = document.createElement("p");
        who.className = "inr-sheet__sub";
        who.textContent = "You're hitching as @" + window.USERNAME;
        sheet.appendChild(who);
      }

      const field = document.createElement("div");
      field.className = "inr-field";
      const chips = document.createElement("div");
      chips.className = "inr-cohitch-chips";
      field.appendChild(chips);

      const inputWrap = document.createElement("div");
      inputWrap.className = "inr-cohitch-inputwrap";
      const input = document.createElement("input");
      input.type = "text";
      input.className = "inr-cohitch-input";
      input.setAttribute("autocomplete", "off");
      input.setAttribute("maxlength", "32");
      input.placeholder = "Add co-hitchhiker username…";
      const suggest = document.createElement("ul");
      suggest.className = "inr-cohitch-suggest";
      suggest.style.display = "none";
      inputWrap.appendChild(input);
      inputWrap.appendChild(suggest);
      field.appendChild(inputWrap);
      sheet.appendChild(field);

      function renderChips() {
        chips.innerHTML = "";
        selected.forEach(function (name) {
          const chip = document.createElement("span");
          chip.className = "inr-cohitch-chip";
          chip.textContent = name;
          const x = document.createElement("button");
          x.type = "button";
          x.className = "inr-cohitch-chip__x";
          x.setAttribute("aria-label", "Remove " + name);
          x.innerHTML = "&times;";
          x.addEventListener("click", function () {
            const i = selected.indexOf(name);
            if (i !== -1) selected.splice(i, 1);
            renderChips();
          });
          chip.appendChild(x);
          chips.appendChild(chip);
        });
      }

      function addName(name) {
        name = (name || "").trim();
        // Skip blanks, the creator's own username, and duplicates (case-insensitive).
        if (!name || name.toLowerCase() === self) { input.value = ""; return; }
        if (selected.some(function (n) { return n.toLowerCase() === name.toLowerCase(); })) { input.value = ""; return; }
        selected.push(name);
        renderChips();
        input.value = "";
        suggest.style.display = "none";
      }

      let debounce = null;
      input.addEventListener("input", function () {
        const q = input.value.trim();
        if (debounce) clearTimeout(debounce);
        if (q.length < 1) { suggest.style.display = "none"; return; }
        debounce = setTimeout(function () {
          fetch("/search_usernames?q=" + encodeURIComponent(q))
            .then(function (r) { return r.json(); })
            .then(function (names) {
              suggest.innerHTML = "";
              if (!names || names.length === 0) { suggest.style.display = "none"; return; }
              names.forEach(function (name) {
                const li = document.createElement("li");
                li.textContent = name;
                // mousedown (not click) so it fires before the input's blur.
                li.addEventListener("mousedown", function (e) { e.preventDefault(); addName(name); });
                suggest.appendChild(li);
              });
              suggest.style.display = "block";
            })
            .catch(function () { suggest.style.display = "none"; });
        }, 200);
      });

      const startBtn = document.createElement("button");
      startBtn.type = "button";
      startBtn.className = "inr-big inr-big--green inr-sheet__save";
      startBtn.innerHTML = '<i class="fa-solid fa-thumbs-up"></i> Start hitching';
      startBtn.addEventListener("click", function () {
        // Fold a half-typed username into the list so it isn't silently lost.
        if (input.value.trim()) addName(input.value);
        const list = selected.slice();
        close();
        onStart(list);
      });
      sheet.appendChild(startBtn);

      function close() {
        if (scrim.parentNode) scrim.parentNode.removeChild(scrim);
        if (sheet.parentNode) sheet.parentNode.removeChild(sheet);
        journeyUI._openDialog = null;
      }
      // Scrim tap dismisses WITHOUT starting (abort) — no journey begins.
      scrim.addEventListener("click", close);

      document.body.appendChild(scrim);
      document.body.appendChild(sheet);
      journeyUI._openDialog = { close };
      return { close };
    },
```

- [ ] **Step 3: Add `beginWithCoHitchers` and route the three new-start sites**

In `hitch/static/inride.js`, add the helper (near `journeyFlow.start`):

```js
  // Show the co-hitcher modal, then seed the journey with whoever was added.
  journeyFlow.beginWithCoHitchers = function (latlng) {
    journeyUI.coHitcherSheet(function (coHitchhikers) {
      journeyFlow.start(latlng, coHitchhikers);
    });
  };
```

Then change the three new-journey start sites to call it instead of `start` directly:

1. `startFromChoose` logged-in branch — currently `if (window.IS_LOGGED_IN) return journeyFlow.start(latlng);` →

```js
    if (window.IS_LOGGED_IN) return journeyFlow.beginWithCoHitchers(latlng);
```

2. "Continue anonymously" action — currently `onClick: () => journeyFlow.start(latlng)` →

```js
        { label: "Continue anonymously", cls: "inr-grey", onClick: () => journeyFlow.beginWithCoHitchers(latlng) },
```

3. Post-login-redirect resume — currently `try { const p = JSON.parse(pend); journeyFlow.start(L.latLng(p.lat, p.lon)); return; } catch (e) {}` →

```js
      try { const p = JSON.parse(pend); journeyFlow.beginWithCoHitchers(L.latLng(p.lat, p.lon)); return; } catch (e) {}
```

(Leave every other `journeyFlow.start(...)` call — e.g. resuming an already-started journey — unchanged, so the modal only appears for new starts.)

- [ ] **Step 4: Add modal styles**

In `hitch/static/style.css`, append (near the other `.inr-sheet` rules):

```css
/* Co-hitcher modal: username chips + autocomplete dropdown. */
.inr-cohitch-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.inr-cohitch-chip {
  display: inline-flex; align-items: center; gap: 6px;
  background: #e8f0fe; color: #1a73e8; border-radius: 14px;
  padding: 4px 10px; font-size: 14px; font-weight: 600;
}
.inr-cohitch-chip__x {
  border: none; background: transparent; color: #1a73e8;
  font-size: 16px; line-height: 1; cursor: pointer; padding: 0;
}
.inr-cohitch-inputwrap { position: relative; }
.inr-cohitch-input {
  width: 100%; box-sizing: border-box; padding: 10px 12px;
  border: 1px solid #ccc; border-radius: 8px; font-size: 15px;
}
.inr-cohitch-suggest {
  position: absolute; left: 0; right: 0; top: 100%; z-index: 10;
  list-style: none; margin: 2px 0 0; padding: 0; background: #fff;
  border: 1px solid #ccc; border-radius: 8px; max-height: 200px; overflow-y: auto;
  box-shadow: 0 4px 12px rgba(0, 0, 0, .15);
}
.inr-cohitch-suggest li { padding: 8px 12px; cursor: pointer; border-bottom: 1px solid #eee; }
.inr-cohitch-suggest li:hover { background: #f0f0f0; }
```

- [ ] **Step 5: Verify it parses**

Run: `node --check hitch/static/inride.js`
Expected: OK.

- [ ] **Step 6: On-device verification** (no unit-test surface for this DOM flow)

Confirm each on the device/tunnel:
1. Logged in → "Start Hitching" (and "Hitch here") → modal shows "You're hitching as @<you>"; add a co-hitcher via autocomplete; "Start hitching" begins the waiting journey.
2. Logged out → "Start Hitching" → "Track your rides?" → "Continue anonymously" → modal (no username line) → add name → start.
3. Log in via the "Log in" path → after returning, the modal appears (post-login resume), then starts.
4. You cannot add your own username; duplicates are ignored; scrim/× aborts with no journey started.
5. Finish a ride with a co-hitcher and confirm the invite lands (the co-hitcher's account gets the pending invite); repeat with Give Up.
6. Reload mid-wait → journey (and co-hitchers) restored; the modal does NOT reappear.

- [ ] **Step 7: Commit**

```bash
git add hitch/static/inride.js hitch/static/style.css
git commit -m "feat(inride): co-hitcher modal at journey start"
```

---

## Self-Review

- **Spec coverage:** `window.USERNAME` (Task 1) ✓; co-hitchers on the journey + Finish + Give Up carry-through (Task 2 builders, Task 3 storage) ✓; modal reusing `/search_usernames`, optional, no Skip, self-exclusion + dedupe, dismiss aborts (Task 3) ✓; all three new-start entry points routed, resume-of-existing untouched (Task 3 Step 3) ✓; anonymous line omitted (Task 3 Step 2) ✓; backend reuse — no new write logic (Global Constraints; nothing in the plan adds `CoHitchhiker` writes) ✓.
- **Placeholder scan:** none — every step has concrete code/commands.
- **Type consistency:** `coHitchhikers` (array) is the journey field throughout; `co_hitchhiker` (CSV string) is the wire field in both builders and matches the `/ride` handler; `buildGiveUpBody(j, waitMin, details, id)` signature is used identically in the test and the `giveUp` call site; `beginWithCoHitchers(latlng)` and `coHitcherSheet(onStart)` names match across definition and call sites.
