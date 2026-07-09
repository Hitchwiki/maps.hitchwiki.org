# Durable Ride Outbox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Never lose a ride log to bad connectivity — Finish and Give Up write to a durable localStorage outbox first, then upload automatically (idempotently) when the network returns.

**Architecture:** A localStorage-backed outbox (`inride.outbox`) sits beside the existing `journeyStore`. Finish/Give Up enqueue a submission (with a client-generated `d_tag`) before any network call, so the journey always completes. A flush engine POSTs pending items to `/ride`, classifying results as success / transient (retry) / permanent (flag). Because ride events are Nostr kind 36820 (replaceable), reusing the client `d_tag` on retries makes them idempotent — no duplicates.

**Tech Stack:** Vanilla JS (no framework), Leaflet, Flask, pytest. No new dependencies. No service worker.

**Spec:** `docs/superpowers/specs/2026-07-08-durable-ride-outbox-design.md`

## Global Constraints

- Branch: `feature/in-ride-hitching-tracker` (do NOT branch off; continue here).
- No new runtime dependencies; vanilla JS only, matching `hitch/static/inride.js` style (IIFE, `var`/`const`, no build step).
- Requirement comments above non-obvious logic explaining the "why" (per CLAUDE.md).
- `ruff check` / `ruff format` clean for Python (line length 130).
- Backend ride submission is detected as in-ride via header `X-Requested-With: inride` → returns JSON (existing behavior, `main.py:533`).
- Ride events are Nostr kind 36820 (parameterized replaceable): same `(pubkey, kind, d_tag)` replaces. Client-supplied `d_tag` is a bare uuid; the server prefixes it with `record.source`.
- Frontend has no JS unit-test harness; frontend tasks are verified manually via the running app (tunnel), matching the existing in-ride plan convention. Backend tasks use pytest.
- The public JS namespace is `window.inride = { journeyStore, journeyUI, journeyFlow }` (`inride.js:1204`); attach new modules there.

---

### Task 1: Backend — idempotent client-supplied `d_tag`

**Files:**
- Modify: `hitch/blueprints/utils/post_hitchhiking_ride_to_nostr.py:56-113` (`post`)
- Modify: `hitch/blueprints/main.py:674-681` (new-ride branch of `ride_form` POST)
- Test: `tests/test_inride_outbox.py` (new)

**Interfaces:**
- Consumes: existing `HitchhikingDataStandardToNostrPoster.post(ride_record, tags=None)`.
- Produces: `post(ride_record, tags=None, d_tag=None)` — when `d_tag` is a non-empty string and `tags is None`, the event's `d` tag is `f"{ride_record.source}-{d_tag}"`. `POST /ride` reads optional form field `client_d_tag` and threads it through.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_inride_outbox.py
# The outbox retries a submission with the SAME client d_tag. Because ride events are
# replaceable (kind 36820), the server MUST reuse that d_tag so a retry replaces rather
# than duplicates. This test pins the poster's d_tag-construction contract.
from unittest.mock import patch
from hitch.blueprints.utils.post_hitchhiking_ride_to_nostr import HitchhikingDataStandardToNostrPoster


def test_post_uses_client_d_tag_when_provided():
    poster = HitchhikingDataStandardToNostrPoster()

    captured = {}

    # Stub the actual signing/relay send so we only assert the d tag that gets built.
    def fake_send(event):
        captured["event"] = event

    class FakeRecord:
        source = "hitchmap"

        def to_custom_object(self):
            return {}

    with patch.object(poster, "_sign_and_send", side_effect=fake_send, create=True):
        returned_d = poster.post(ride_record=FakeRecord(), d_tag="abc-123")

    assert returned_d == "hitchmap-abc-123"
```

Note: adapt `_sign_and_send` / `to_custom_object` to the poster's real internal method names — open `post_hitchhiking_ride_to_nostr.py` and patch whatever `post()` actually calls to build+send the event, so the test exercises only the d_tag branch. If the real `post` is hard to stub, assert on the return value alone (it returns the d_tag string) and drop the `captured` scaffolding.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_inride_outbox.py::test_post_uses_client_d_tag_when_provided -v`
Expected: FAIL — `post()` has no `d_tag` parameter (TypeError) or returns a uuid, not `hitchmap-abc-123`.

- [ ] **Step 3: Add the `d_tag` param to `post`**

In `post_hitchhiking_ride_to_nostr.py`, change the signature and the d_tag line:

```python
    def post(self, ride_record: HitchhikingRecord, tags: list = None, d_tag: str = None) -> str:
        ...
        # d tag precedence: an edit passes existing `tags` (reuse its d); a new ride from the
        # offline outbox passes a client-generated `d_tag` (reuse so retries replace, not
        # duplicate — kind 36820 is replaceable); otherwise mint a fresh uuid. Source stays
        # server-authoritative — the client supplies only the bare id.
        if tags is not None:
            d_tag = next(tag[1] for tag in tags if tag[0] == "d")
        elif d_tag:
            d_tag = f"{ride_record.source}-{d_tag}"
        else:
            d_tag = f"{ride_record.source}-{uuid.uuid4()}"
```

(Replace the existing single-line `d_tag = ...` assignment at `:78` with the block above.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_inride_outbox.py::test_post_uses_client_d_tag_when_provided -v`
Expected: PASS

- [ ] **Step 5: Thread `client_d_tag` through `POST /ride`**

In `hitch/blueprints/main.py`, new-ride branch (`:674-681`), pass the form field:

```python
        else:
            # This is a new ride - normal flow
            # TODO: define license properly instead of using "xxx"
            record = create_record_from_custom_object(custom_object=data, source=THIS_NOSTR_SOURCE, license=THIS_DATA_LICENSE)

            poster = HitchhikingDataStandardToNostrPoster()
            # Offline outbox retries carry a stable client-supplied d_tag so a resend
            # replaces the same event instead of creating a duplicate ride.
            client_d_tag = (data.get("client_d_tag") or "").strip() or None
            d_tag = poster.post(ride_record=record, d_tag=client_d_tag)
            poster.close()
```

- [ ] **Step 6: Write the round-trip idempotency test**

```python
def test_ride_post_is_idempotent_on_client_d_tag(client, monkeypatch):
    # Two POSTs with the same client_d_tag must yield the same server d tag, proving a
    # retry replaces rather than duplicates. Stub the poster so no real relay is needed.
    seen = []

    def fake_post(self, ride_record, tags=None, d_tag=None):
        d = f"{ride_record.source}-{d_tag}" if d_tag else f"{ride_record.source}-generated"
        seen.append(d)
        return d

    monkeypatch.setattr(
        "hitch.blueprints.main.HitchhikingDataStandardToNostrPoster.post", fake_post, raising=True
    )
    monkeypatch.setattr(
        "hitch.blueprints.main.HitchhikingDataStandardToNostrPoster.close", lambda self: None, raising=True
    )

    form = {
        "rate": "4", "wait": "10", "comment": "", "signal": "", "vehicle_kind": "",
        "pickup_lat": "52.0", "pickup_lon": "13.0",
        "destination_lat": "", "destination_lon": "",
        "client_d_tag": "fixed-uuid-1",
    }
    headers = {"X-Requested-With": "inride"}
    r1 = client.post("/ride", data=form, headers=headers)
    r2 = client.post("/ride", data=form, headers=headers)
    assert r1.json["ok"] and r2.json["ok"]
    assert r1.json["d_tag"] == r2.json["d_tag"] == "hitchmap-fixed-uuid-1"
```

Reuse the `client` fixture style from `tests/test_inride_submit.py`. If `THIS_NOSTR_SOURCE` is not `hitchmap`, change the expected value to `f"{THIS_NOSTR_SOURCE}-fixed-uuid-1"`.

- [ ] **Step 7: Run both tests**

Run: `python -m pytest tests/test_inride_outbox.py -v`
Expected: PASS (both). Then `ruff check hitch/ tests/ && ruff format hitch/ tests/`.

- [ ] **Step 8: Commit**

```bash
git add hitch/blueprints/utils/post_hitchhiking_ride_to_nostr.py hitch/blueprints/main.py tests/test_inride_outbox.py
git commit -m "feat(inride): accept client-supplied d_tag for idempotent ride retries"
```

---

### Task 2: Backend — relay failure returns JSON 503 (transient)

**Files:**
- Modify: `hitch/blueprints/main.py:719-722` (exception tail of `ride_form` POST)
- Test: `tests/test_inride_outbox.py`

**Interfaces:**
- Produces: when the Nostr publish raises a connection/relay error (not a validation error), the JSON path returns `({"ok": False, "error": ..., "transient": True}, 503)` so the client retries instead of flagging a permanent failure. Validation errors keep `({"ok": False, "error": ...}, 400)` (no `transient`).

- [ ] **Step 1: Write the failing test**

```python
def test_ride_post_relay_failure_is_transient_503(client, monkeypatch):
    # A dead relay must NOT look like a validation error. The client classifies 400 as
    # permanent (flag for manual retry) and 5xx/503 as transient (auto-retry) — so relay
    # outages have to return 503 with transient:true, else queued rides get wrongly flagged.
    def boom(self, ride_record, tags=None, d_tag=None):
        raise ConnectionError("relay unreachable")

    monkeypatch.setattr(
        "hitch.blueprints.main.HitchhikingDataStandardToNostrPoster.post", boom, raising=True
    )
    monkeypatch.setattr(
        "hitch.blueprints.main.HitchhikingDataStandardToNostrPoster.close", lambda self: None, raising=True
    )
    form = {
        "rate": "4", "wait": "10", "comment": "", "signal": "", "vehicle_kind": "",
        "pickup_lat": "52.0", "pickup_lon": "13.0",
        "destination_lat": "", "destination_lon": "", "client_d_tag": "x1",
    }
    r = client.post("/ride", data=form, headers={"X-Requested-With": "inride"})
    assert r.status_code == 503
    assert r.json["ok"] is False and r.json["transient"] is True
```

- [ ] **Step 2: Run it to verify failure**

Run: `python -m pytest tests/test_inride_outbox.py::test_ride_post_relay_failure_is_transient_503 -v`
Expected: FAIL — a `ConnectionError` escapes the `except (AssertionError, ValueError, KeyError)` clause and 500s (or the test can't parse JSON).

- [ ] **Step 3: Add a transient exception branch**

In `main.py`, extend the exception tail (`:719-722`):

```python
    except (AssertionError, ValueError, KeyError) as err:
        # Bad input — permanent. 400 with no `transient` flag; the outbox flags it for
        # manual retry/discard rather than looping forever.
        if wants_json:
            return jsonify({"ok": False, "error": str(err)}), 400
        raise
    except Exception as err:
        # Anything else during publish (relay unreachable, timeout, signing hiccup) is
        # transient — tell the JSON client to keep the item queued and retry later.
        if wants_json:
            return jsonify({"ok": False, "error": str(err), "transient": True}), 503
        raise
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_inride_outbox.py -v`
Expected: PASS (all). Then `ruff check hitch/ && ruff format hitch/`.

- [ ] **Step 5: Commit**

```bash
git add hitch/blueprints/main.py tests/test_inride_outbox.py
git commit -m "feat(inride): return JSON 503 transient on relay/publish failure"
```

---

### Task 3: Frontend — `outboxStore` + `uuid` helper

**Files:**
- Modify: `hitch/static/inride.js` (add `uuid()` near the helpers `~:49`; add `outboxStore` after `journeyStore` `~:24`; extend `window.inride` at `:1204`)

**Interfaces:**
- Produces:
  - `uuid()` → RFC-4122-ish v4 string (uses `crypto.randomUUID()` when available, else a fallback).
  - `outboxStore` with: `get()` → array (corruption-safe), `set(list)`, `add(item)` → item, `remove(id)`, `update(id, patch)` → item|null, `pending()` → items with `status !== "failed"`, `count()` → number.
  - Item shape: `{ id, kind, body, createdAt, attempts, lastError, status }`.
  - Attached to `window.inride.outboxStore`.

- [ ] **Step 1: Add `uuid()` helper**

After `fmtHMS` (`inride.js:~56`):

```js
  // Stable id for an outbox item; also becomes the Nostr d_tag so retries are idempotent.
  function uuid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
      const r = (Math.random() * 16) | 0, v = c === "x" ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }
```

- [ ] **Step 2: Add `outboxStore`**

After `journeyStore` (`inride.js:~24`):

```js
  // Durable queue of ride submissions that haven't reached the server yet. Lives in
  // localStorage beside the journey so a Finish/Give Up survives an offline stretch, a
  // reload, or an app restart. status:"failed" = permanent (validation) — not auto-retried.
  const OUTBOX_KEY = "inride.outbox";
  const outboxStore = {
    get() {
      try { const v = JSON.parse(localStorage.getItem(OUTBOX_KEY)); return Array.isArray(v) ? v : []; }
      catch (e) { return []; }
    },
    set(list) { localStorage.setItem(OUTBOX_KEY, JSON.stringify(list)); return list; },
    add(item) { const l = outboxStore.get(); l.push(item); outboxStore.set(l); return item; },
    remove(id) { outboxStore.set(outboxStore.get().filter((it) => it.id !== id)); },
    update(id, patch) {
      const l = outboxStore.get();
      const it = l.find((x) => x.id === id);
      if (!it) return null;
      Object.assign(it, patch);
      outboxStore.set(l);
      return it;
    },
    pending() { return outboxStore.get().filter((it) => it.status !== "failed"); },
    count() { return outboxStore.get().length; },
  };
```

- [ ] **Step 3: Expose on the namespace**

Change `inride.js:1204`:

```js
  window.inride = { journeyStore, journeyUI, journeyFlow, outboxStore }; // more attached in later tasks
```

- [ ] **Step 4: Syntax check**

Run: `node --check hitch/static/inride.js`
Expected: no output (OK).

- [ ] **Step 5: Manual verify (browser console, via tunnel)**

In the console:
```js
inride.outboxStore.set([]);
inride.outboxStore.add({ id: inride.outboxStore, kind: "finish", body: {}, createdAt: 1, attempts: 0, lastError: null, status: "pending" });
inride.outboxStore.add({ id: "b", kind: "giveup", body: {}, createdAt: 2, attempts: 0, lastError: null, status: "failed" });
console.log(inride.outboxStore.count(), inride.outboxStore.pending().length); // 2 1
inride.outboxStore.update("b", { status: "pending" });
console.log(inride.outboxStore.pending().length); // 2
inride.outboxStore.remove("b");
console.log(inride.outboxStore.count()); // 1
inride.outboxStore.set([]);
```
Expected: logs `2 1`, then `2`, then `1`.

- [ ] **Step 6: Commit**

```bash
git add hitch/static/inride.js
git commit -m "feat(inride): outboxStore + uuid helper (durable submission queue)"
```

---

### Task 4: Frontend — `flushOutbox` engine

**Files:**
- Modify: `hitch/static/inride.js` (add `submitBody`, `flushOutbox` near `submitRide` `~:73`; extend `window.inride`)

**Interfaces:**
- Consumes: `outboxStore`, `outboxUI.refresh` (Task 8 — call defensively: `if (window.inride.outboxUI) window.inride.outboxUI.refresh()`).
- Produces:
  - `submitBody(body)` → `Promise<{status:number, json:object|null}>` — POSTs a form body to `/ride` with the inride header; never throws (network error → `{status:0, json:null}`).
  - `flushOutbox()` → `Promise<void>` — drains `outboxStore.pending()`, classifying each: success → remove; permanent (400, not transient) → mark `failed`; transient (0/5xx/unparseable) → bump `attempts`. Guarded by a module `flushing` flag against overlap.
  - Attached to `window.inride.flushOutbox`.

- [ ] **Step 1: Add `submitBody` + `flushOutbox`**

Replace the existing `submitRide` (`inride.js:73-94`) region by ADDING these alongside it (keep `submitRide` for now; Task 5 removes its caller). Place after `submitRide`:

```js
  // POST a saved outbox body to /ride. Resolves with {status, json}; a thrown network
  // error resolves as {status:0} (not a rejection) so the flush loop can classify it.
  function submitBody(body) {
    return fetch("/ride", {
      method: "POST",
      headers: { "X-Requested-With": "inride", "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams(body),
    })
      .then(function (r) { return r.json().then(function (j) { return { status: r.status, json: j }; },
                                              function () { return { status: r.status, json: null }; }); })
      .catch(function () { return { status: 0, json: null }; });
  }

  // Drain pending outbox items. Classification:
  //   success  (200 ok:true)          → remove
  //   permanent(400 ok:false !transient) → mark "failed" (needs manual retry/discard)
  //   transient(0 / 5xx / unparseable)  → keep, bump attempts, try again later
  // A single `flushing` guard prevents the interval + online-event + enqueue triggers
  // from overlapping and double-submitting the same item.
  let flushing = false;
  function flushOutbox() {
    if (flushing) return Promise.resolve();
    const items = outboxStore.pending();
    if (!items.length) return Promise.resolve();
    flushing = true;

    // Sequential (reduce) so we don't fan out N parallel POSTs on a flaky link.
    return items.reduce(function (chain, item) {
      return chain.then(function () {
        return submitBody(item.body).then(function (res) {
          if (res.json && res.json.ok) {
            outboxStore.remove(item.id);
          } else if (res.status === 400 && res.json && res.json.transient !== true) {
            outboxStore.update(item.id, {
              status: "failed",
              lastError: (res.json && res.json.error) || "Rejected",
              attempts: item.attempts + 1,
            });
          } else {
            outboxStore.update(item.id, {
              lastError: (res.json && res.json.error) || "Offline",
              attempts: item.attempts + 1,
            });
          }
        });
      });
    }, Promise.resolve()).then(function () {
      flushing = false;
      if (window.inride.outboxUI) window.inride.outboxUI.refresh();
    }, function () {
      flushing = false; // never leave the guard stuck on an unexpected throw
    });
  }
```

- [ ] **Step 2: Expose on the namespace**

```js
  window.inride = { journeyStore, journeyUI, journeyFlow, outboxStore, submitBody, flushOutbox };
```

- [ ] **Step 3: Syntax check**

Run: `node --check hitch/static/inride.js`
Expected: OK.

- [ ] **Step 4: Manual verify — transient path (no relay running)**

The test env's dummy relay is down, so a real POST returns transient. In the console:
```js
inride.outboxStore.set([]);
inride.outboxStore.add({ id: "t1", kind: "finish", createdAt: Date.now(), attempts: 0, lastError: null, status: "pending",
  body: { rate: "4", wait: "3", comment: "", signal: "", vehicle_kind: "", pickup_lat: "52", pickup_lon: "13",
          destination_lat: "52.1", destination_lon: "13.1", client_d_tag: "t1", datetime_ride: "2026-07-08T10:00", arrival_datetime: "2026-07-08T10:20" } });
await inride.flushOutbox();
console.log(inride.outboxStore.get()); // still 1 item, attempts: 1, status "pending"
inride.outboxStore.set([]);
```
Expected: the item remains, `attempts` incremented to 1, still `pending` (relay down = transient). If you point the app at a live relay, the same call removes the item (success).

- [ ] **Step 5: Commit**

```bash
git add hitch/static/inride.js
git commit -m "feat(inride): flushOutbox engine with transient/permanent classification"
```

---

### Task 5: Frontend — Finish enqueues instead of posting inline

**Files:**
- Modify: `hitch/static/inride.js` — `submitRide` (`:73-94`, replaced by a body-builder), `completeFinish` (`:98-113`), `journeyFlow.finish` (`:200-221`)

**Interfaces:**
- Consumes: `outboxStore`, `flushOutbox`, `uuid`, `isoLocal`, `journeyUI.toast` (add a small toast helper here).
- Produces:
  - `buildFinishBody(j, dest, finishMs)` → the form-body object (was `submitRide`'s URLSearchParams contents), now including `client_d_tag`.
  - `completeFinish(j, dest, finishMs)` → enqueues, clears busy, proceeds to `whatsNext`, flushes, and toasts if offline. No inline error banner (the outbox owns retries now).
  - `journeyUI.toast(msg)` → brief non-blocking bottom toast.

- [ ] **Step 1: Add `journeyUI.toast`**

Add to the `journeyUI` object (near `error`, `inride.js:~745`):

```js
    // Brief, non-blocking confirmation (distinct from error()'s red banner). Used to tell
    // the user a ride was safely queued when they're offline. Auto-removes after 4 s.
    toast(msg) {
      const t = document.createElement("div");
      t.className = "inr-toast";
      t.textContent = msg;
      document.body.appendChild(t);
      setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 4000);
    },
```

- [ ] **Step 2: Replace `submitRide` with `buildFinishBody`**

Replace `inride.js:73-94` (`function submitRide ...`) with:

```js
  // Build the /ride form body from a journey + destination. client_d_tag pins the Nostr
  // d_tag so outbox retries replace rather than duplicate. finishMs is the arrival stamp.
  function buildFinishBody(j, dest, finishMs, id) {
    const d = j.details || {};
    return {
      rate: String(d.rating || ""),
      wait: String(Math.round((j.finalWaitMs || 0) / 60000)),
      signal: (d.signal || []).join(","),
      comment: d.comment || "",
      vehicle_kind: d.vehicle_kind || "",
      pickup_lat: j.pickup.lat, pickup_lon: j.pickup.lon,
      destination_lat: dest.lat, destination_lon: dest.lon,
      datetime_ride: isoLocal(j.gotRideMs),
      arrival_datetime: isoLocal(finishMs),
      client_d_tag: id,
    };
  }
```

- [ ] **Step 3: Rewrite `completeFinish` to enqueue**

Replace `inride.js:98-113` (`function completeFinish ...`) with:

```js
  // Enqueue the finished ride durably, THEN proceed — the journey never blocks on the
  // network. The outbox flush (now + on reconnect) performs the actual upload. If the
  // enqueue happens while offline, reassure the user the ride is saved.
  function completeFinish(j, dest, finishMs) {
    const id = uuid();
    outboxStore.add({
      id: id, kind: "finish", createdAt: Date.now(), attempts: 0, lastError: null, status: "pending",
      body: buildFinishBody(j, dest, finishMs, id),
    });
    journeyUI.setFinishBusy(false);
    if (window.inride.outboxUI) window.inride.outboxUI.refresh();
    startOutboxTimer(); // Task 9 helper; safe no-op guard below until then
    if (navigator.onLine === false) {
      journeyUI.toast("Saved — will upload when you're back online.");
    }
    journeyFlow.whatsNext(dest);
    flushOutbox();
  }
```

Add a temporary guard so Steps compile before Task 9 defines `startOutboxTimer` — put this near the helpers now and Task 9 will replace its body:

```js
  // Replaced in Task 9 with the real interval starter.
  function startOutboxTimer() {}
```

- [ ] **Step 4: `journeyFlow.finish` — no functional change to GPS/manual-pin**

`finish` already calls `completeFinish` on GPS success and after manual-pin confirm. Leave it; it now enqueues via the rewritten `completeFinish`. Confirm the two call sites (`inride.js:209` and `:217`) still pass `(j, dest, finishMs)`.

- [ ] **Step 5: Add the toast CSS**

In `hitch/static/style.css` (near `.inr-chip`):

```css
/* Non-blocking "saved offline" confirmation toast — sits above the dock stack. */
.inr-toast {
  position: fixed;
  left: 50%;
  transform: translateX(-50%);
  bottom: calc(var(--bottom-pane-h, env(safe-area-inset-bottom, 0px)) + 160px);
  z-index: 2003;
  background: rgba(17, 17, 17, .92);
  color: #fff;
  border-radius: 12px;
  padding: 10px 16px;
  font-size: 13.5px;
  font-weight: 600;
  max-width: 88vw;
  text-align: center;
  box-shadow: 0 3px 10px rgba(0, 0, 0, .3);
}
```

- [ ] **Step 6: Syntax check + manual verify**

Run: `node --check hitch/static/inride.js`
Manual (tunnel, device): start a journey → Got a Ride → Finish Ride → allow GPS (or deny → drop pin → Confirm). Because the relay is down, the journey still advances to "What's next?" and a `⟳ 1 to upload` chip appears (Task 8 renders it; until then check `inride.outboxStore.count()` in console = 1). No red "Couldn't save" banner. Toggle DevTools offline before Finish → the toast appears.

- [ ] **Step 7: Commit**

```bash
git add hitch/static/inride.js hitch/static/style.css
git commit -m "feat(inride): Finish enqueues to the outbox instead of posting inline"
```

---

### Task 6: Frontend — Give Up captures inline and enqueues

**Files:**
- Modify: `hitch/static/inride.js` — `journeyFlow.giveUp` (`:175-184`); add `giveUpSheet` (trim of `rideDetailsSheet` `:842`)

**Interfaces:**
- Consumes: `journeyUI.rideDetailsSheet` pattern, `outboxStore`, `flushOutbox`, `uuid`, `journeyStore.currentWaitMs`.
- Produces: `journeyUI.giveUpSheet(onSave)` — a slim sheet with **rating (required) + optional comment** only. `giveUp` builds a destination-less body and enqueues.

- [ ] **Step 1: Add `journeyUI.giveUpSheet`**

Model it on `rideDetailsSheet` (`inride.js:842`) but drop the vehicle-kind and signal chips. Title "How was the spot?"; subtitle "You waited here — rate the spot." Required 5-star rating, optional comment, a green "Save" button. On save call `onSave({ rating, comment })`. (Reuse the exact star-rating + comment DOM from `rideDetailsSheet`; omit the chip rows.)

- [ ] **Step 2: Rewrite `journeyFlow.giveUp`**

Replace `inride.js:175-184` with:

```js
  // Gave up waiting. Capture a rating + comment inline (no redirect — the /ride form
  // won't load offline), then enqueue a destination-less ride (backend stores NaN dest).
  // The wait is pause-aware and frozen at give-up time.
  journeyFlow.giveUp = function () {
    const j = journeyStore.get(); if (!j) return;
    const waitMin = Math.round(journeyStore.currentWaitMs(j, Date.now()) / 60000);
    journeyUI.giveUpSheet(function (details) {
      const id = uuid();
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
      journeyStore.clear();
      journeyUI.teardown();
      if (window.inride.outboxUI) window.inride.outboxUI.refresh();
      startOutboxTimer();
      if (navigator.onLine === false) journeyUI.toast("Saved — will upload when you're back online.");
      flushOutbox();
    });
  };
```

- [ ] **Step 3: Syntax check + manual verify**

Run: `node --check hitch/static/inride.js`
Manual: start a journey → **Give Up** → the slim rating sheet appears (no vehicle/signal chips) → try to save with no stars (blocked) → pick 3 stars + a comment → Save → journey chrome clears, `inride.outboxStore.count()` = 1, item `kind:"giveup"`, `body.destination_lat === ""`.

- [ ] **Step 4: Commit**

```bash
git add hitch/static/inride.js
git commit -m "feat(inride): Give Up captures rating inline and enqueues (offline-safe)"
```

---

### Task 7: Frontend — long-press during in-ride drops a Finish pin

**Files:**
- Modify: `hitch/static/inride.js` — `window.inrideOnEntryGesture` (`:1163`, the early `journeyStore.get()` guard at `:1150`... verify exact line)

**Interfaces:**
- Consumes: `journeyStore`, `journeyUI.manualPin`, `journeyFlow` finish internals (`completeFinish`), `getFixWithRetry` not needed here.
- Produces: when a gesture fires and the journey is `in-ride`, open `manualPin` seeded at the pressed latlng; Confirm runs the finish capture at that point. Waiting/paused still swallow gestures.

- [ ] **Step 1: Branch the active-journey guard**

Find the guard in `inrideOnEntryGesture` that returns early when a journey exists (spec references `if (journeyStore.get()) return true;`). Replace it with:

```js
    // One journey at a time. While waiting/paused we swallow map gestures. But in-ride, a
    // long-press is a deliberate "finish here" — drop a destination pin at the pressed
    // point and run the finish capture on Confirm (a gesture alternative to Finish → GPS).
    const active = journeyStore.get();
    if (active) {
      if (active.state === "in-ride") {
        const finishMs = Date.now();
        journeyUI.manualPin(function (dest) {
          journeyUI.setFinishBusy(true);
          completeFinish(active, dest, finishMs);
        }, latlng);
      }
      return true;
    }
```

- [ ] **Step 2: Let `manualPin` accept a seed latlng**

`manualPin(cb)` currently seeds at `window.map.getCenter()` (`inride.js:780`). Add an optional second arg:

```js
    manualPin(cb, seedLatLng) {
      ...
      const marker = L.marker(seedLatLng || window.map.getCenter(), {
```

(Only change the signature line and the `L.marker(...)` seed; the rest is unchanged.)

- [ ] **Step 3: Syntax check + manual verify**

Run: `node --check hitch/static/inride.js`
Manual: get in-ride → long-press a point on the map → the orange destination pin appears there with the "Drop a pin for your destination" card → drag/confirm → the ride enqueues (`outboxStore.count()` +1) and advances to "What's next?". Long-press while *waiting* → nothing happens (still swallowed). Confirm the event markers don't steal the press (Task-from-earlier `inr-picking` covers manualPin).

- [ ] **Step 4: Commit**

```bash
git add hitch/static/inride.js
git commit -m "feat(inride): long-press during a ride drops a finish pin"
```

---

### Task 8: Frontend — pending chip + detail sheet

**Files:**
- Modify: `hitch/static/inride.js` — add `outboxUI` module; call `outboxUI.refresh()` from init and after mutations; extend `window.inride`
- Modify: `hitch/static/style.css` — chip + sheet styles

**Interfaces:**
- Consumes: `outboxStore`, `flushOutbox`, the existing scrim/bottom-card `journeyUI.dialog` pattern.
- Produces: `outboxUI` with `refresh()` (create/update/remove the chip based on `outboxStore`), `openSheet()` (list items; Retry / Discard). Attached to `window.inride.outboxUI`.

- [ ] **Step 1: Build `outboxUI`**

Add a module (near `journeyUI`) that:
- `refresh()`: if `outboxStore.count() === 0`, remove the chip. Else create (once) a fixed pill `#inr-outbox-chip` reading `⟳ N to upload`; add class `inr-outbox-chip--failed` when any item is `status:"failed"` (and swap glyph to `⚠`). Chip click → `openSheet()`.
- `openSheet()`: reuse the scrim + bottom-card. For each item render kind + relative age + (for failed) the error. Buttons: **Retry all** (reset every `failed` item to `pending`, `attempts` kept, then `flushOutbox()` and re-render), per-failed **Discard** (`outboxStore.remove(id)`, confirm via `window.confirm`), and **Close**. Pending items show "waiting for connection…".

Keep it small and DRY with `journeyUI.dialog` where possible; a bespoke list card is fine.

- [ ] **Step 2: Wire `refresh()` into init + mutations**

At the end of `initInride` (`inride.js:~1255`) add `if (window.inride.outboxUI) window.inride.outboxUI.refresh();` so a reload restores the chip. (`completeFinish`/`giveUp`/`flushOutbox` already call `refresh` defensively.)

- [ ] **Step 3: Expose on namespace**

```js
  window.inride = { journeyStore, journeyUI, journeyFlow, outboxStore, submitBody, flushOutbox, outboxUI };
```

- [ ] **Step 4: Chip + sheet CSS**

Add to `style.css`: `#inr-outbox-chip` (fixed, bottom-left, clear of the dock; small dark pill; `z-index:2002`), `.inr-outbox-chip--failed` (red bg), and the list-sheet rows. Mirror the `.inr-chip` / `.location-selection-ui` metrics.

- [ ] **Step 5: Syntax check + manual verify**

Run: `node --check hitch/static/inride.js`
Manual: enqueue a couple of items (finish/give-up while relay down). The `⟳ 2 to upload` chip shows. Tap it → sheet lists both as "waiting". Force one to fail: `inride.outboxStore.update("<id>", {status:"failed", lastError:"Rejected"}); inride.inride ? 0 : inride.outboxUI.refresh()` → chip turns red/⚠. Reopen sheet → the failed item shows its error with **Discard**; **Retry all** resets it to pending and re-flushes. Reload the page → the chip restores from localStorage.

- [ ] **Step 6: Commit**

```bash
git add hitch/static/inride.js hitch/static/style.css
git commit -m "feat(inride): pending-upload chip + detail sheet (retry/discard)"
```

---

### Task 9: Frontend — flush triggers (load, online, interval)

**Files:**
- Modify: `hitch/static/inride.js` — replace the `startOutboxTimer` stub; add load + `online` triggers in the init region (`:1206-1261`)

**Interfaces:**
- Consumes: `flushOutbox`, `outboxStore`.
- Produces: `startOutboxTimer()` starts a ~30 s interval that flushes while items are pending and clears itself when the outbox drains; a `window` `online` listener; a flush on load.

- [ ] **Step 1: Replace the `startOutboxTimer` stub**

```js
  // Periodic flush while items are pending. Self-clearing so an empty outbox costs no
  // timer. Idempotent — safe to call repeatedly (won't stack intervals).
  let outboxTimer = null;
  function startOutboxTimer() {
    if (outboxTimer) return;
    outboxTimer = setInterval(function () {
      if (!outboxStore.pending().length) { clearInterval(outboxTimer); outboxTimer = null; return; }
      flushOutbox();
    }, 30000);
  }
```

- [ ] **Step 2: Add load + online triggers**

In the on-load init region (after `initInride` is defined, near `:1260`), add:

```js
  // Reconnect → drain immediately (don't wait for the interval). Also flush on load and
  // start the timer if a previous session left queued rides.
  window.addEventListener("online", function () { flushOutbox(); });
  function initOutbox() {
    if (window.inride.outboxUI) window.inride.outboxUI.refresh();
    if (outboxStore.pending().length) { flushOutbox(); startOutboxTimer(); }
  }
```

Call `initOutbox()` from the same map-ready gate that calls `initInride()` (`:1260-1261`):

```js
  if (window.map) { initInride(); initOutbox(); }
  else { const t = setInterval(function () { if (window.map) { clearInterval(t); initInride(); initOutbox(); } }, 100); }
```

- [ ] **Step 3: Syntax check + manual verify**

Run: `node --check hitch/static/inride.js`
Manual: with the relay down, enqueue an item → observe a flush attempt every ~30 s (Network tab: repeated `POST /ride`, `attempts` climbing). DevTools → toggle offline then back online → a `POST /ride` fires immediately on the `online` event. Reload with a pending item → it flushes on load and the timer restarts. Point at a live relay (or restore `.env` RELAYS) → the item uploads and the chip disappears.

- [ ] **Step 4: Full regression**

Run: `python -m pytest tests/ -v` (ignore the pre-existing live-relay `test_integration` network failure). Then `ruff check hitch/ tests/ && ruff format hitch/ tests/`.

- [ ] **Step 5: Commit**

```bash
git add hitch/static/inride.js
git commit -m "feat(inride): flush outbox on load, on reconnect, and on interval"
```

---

## Self-Review Notes

- **Spec coverage:** enqueue-before-network (T5/T6), outbox store (T3), idempotent d_tag (T1), transient 503 (T2), flush engine + classification (T4), triggers (T9), pending chip + detail/retry/discard (T8), Give Up inline sheet (T6), long-press finish (T7), toast (T5). All spec sections mapped.
- **Type consistency:** item shape `{id, kind, body, createdAt, attempts, lastError, status}` used identically in T3–T9; `client_d_tag` field name matches backend read in T1; `transient` flag name matches T2 producer / T4 consumer.
- **Ordering:** backend (T1–T2) first so idempotency exists before the client relies on it; `startOutboxTimer` stub in T5 is replaced in T9 (noted at both sites).
