// In-ride hitching tracker. A localStorage-backed state machine layered on the
// map. State + timestamps survive reloads so timing keeps running across a long
// wait or an app restart. See docs/superpowers/specs/2026-07-02-in-ride-hitching-tracker-design.md
(function () {
  "use strict";

  const KEY = "inride.journey";
  const PENDING_KEY = "inride.pendingStart"; // only across the login redirect

  const journeyStore = {
    get() {
      try { return JSON.parse(localStorage.getItem(KEY)); } catch (e) { return null; }
    },
    set(j) { localStorage.setItem(KEY, JSON.stringify(j)); return j; },
    clear() { localStorage.removeItem(KEY); },

    // Active wait in ms: banked segments + the running segment (0 while paused).
    // Authoritative value for the timer/label so reloads AND pauses stay exact.
    currentWaitMs(j, nowMs) {
      if (!j) return 0;
      const running = j.waitSegmentStartMs ? nowMs - j.waitSegmentStartMs : 0;
      return (j.waitAccumMs || 0) + Math.max(0, running);
    },
  };

  // Durable queue of ride submissions that haven't reached the server yet. Lives in
  // localStorage beside the journey so a Finish/Give Up survives an offline stretch, a
  // reload, or an app restart. status:"failed" = permanent (validation) — not auto-retried.
  // Item shape: { id, kind:"finish"|"giveup", body, createdAt, attempts, lastError, status }.
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

  // ── GPS helper ───────────────────────────────────────────────────────────────
  // A GPS "fix" = up to 3 attempts. Timeout / position-unavailable → retry;
  // PERMISSION_DENIED (code 1) is terminal and rejects immediately so the caller
  // can fall back to a manual pin without pointlessly retrying.
  function getFixWithRetry({ tries = 3, timeout = 10000 } = {}) {
    return new Promise((resolve, reject) => {
      let n = 0;
      const attempt = () => {
        n++;
        navigator.geolocation.getCurrentPosition(
          (pos) => resolve({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
          (err) => {
            if (err.code === 1) return reject({ code: "denied" });
            if (n < tries) return attempt();
            reject({ code: "unavailable" });
          },
          { enableHighAccuracy: true, timeout, maximumAge: 0 }
        );
      };
      attempt();
    });
  }

  // ── Helpers ──────────────────────────────────────────────────────────────────
  // Format milliseconds as HH:MM:SS for the waiting chip.
  function fmtHMS(ms) {
    const s = Math.floor(ms / 1000), h = Math.floor(s / 3600),
          m = Math.floor((s % 3600) / 60), ss = s % 60;
    const p = (n) => String(n).padStart(2, "0");
    return `${p(h)}:${p(m)}:${p(ss)}`;
  }

  // Stable id for an outbox item; also becomes the Nostr d_tag so retries are idempotent.
  function uuid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
      const r = (Math.random() * 16) | 0, v = c === "x" ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  // buildFinishBody lives in ride_submit.js (loaded before this file) so it
  // can be unit-tested outside the DOM. Alias it locally to keep call sites unchanged.
  const buildFinishBody = window.RideSubmit.buildFinishBody;

  // Weights + choice lists for the in-ride details sheet, fetched once. Kept module-level
  // so the sheet can render and score synchronously after load. Both are small and cached
  // by the browser; failures leave the sheet usable with empty pickers.
  let _scoreWeights = null;
  let _choices = null;
  function loadDemographicData() {
    const w = _scoreWeights
      ? Promise.resolve(_scoreWeights)
      : fetch("/static/ride_score_weights.json").then(function (r) { return r.json(); }).then(function (j) { _scoreWeights = j; }).catch(function () {});
    const c = _choices
      ? Promise.resolve(_choices)
      : fetch("/driver_info_choices.json").then(function (r) { return r.json(); }).then(function (j) { _choices = j; }).catch(function () {});
    return Promise.all([w, c]);
  }
  function demographicScores(fields) {
    if (!_scoreWeights || !window.RideScore) {
      return { driver: { pct: 0 }, vehicle: { pct: 0, bonusEligible: false }, total: 0, maxTotal: 0, pct: 0 };
    }
    return window.RideScore.computeScores(fields, _scoreWeights);
  }

  // Seal an in-ride overlay so taps on it never reach the Leaflet map. The dock/chip
  // float over the live map with no scrim, and every button tears the overlay down via
  // render(); on touch that lets Leaflet treat the tap as a map click, firing
  // handleMapClick's tap-to-nearest-spot and opening the spot *underneath* the button.
  // disableClickPropagation marks the pointer sequence so the map handler skips it —
  // the same guard map.js already applies to its other overlays.
  function sealTaps(el) {
    if (el && window.L && L.DomEvent) {
      L.DomEvent.disableClickPropagation(el);
      L.DomEvent.disableScrollPropagation(el);
    }
  }

  // POST a saved outbox body to /ride. Resolves with {status, json}; a thrown network
  // error resolves as {status:0} (not a rejection) so the flush loop can classify it.
  function submitBody(body) {
    // Test-mode dry-run (heatmap-button easter egg): never hit the network, so nothing
    // reaches the real DB / Nostr. Resolve as a success so the outbox + UI flow behaves
    // exactly as a real upload (chip clears, "saved", what's-next).
    if (localStorage.getItem("inride.testMode") === "1") {
      console.log("[test mode] skipped /ride POST", body);
      return Promise.resolve({ status: 200, json: { ok: true, d_tag: "test-" + (body.client_d_tag || "") } });
    }
    return fetch("/ride", {
      method: "POST",
      headers: { "X-Requested-With": "inride", "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams(body),
    })
      .then(function (r) {
        return r.json().then(
          function (j) { return { status: r.status, json: j }; },
          function () { return { status: r.status, json: null }; }
        );
      })
      .catch(function () { return { status: 0, json: null }; });
  }

  // Drain pending outbox items. Classification:
  //   success  (200 ok:true)             → remove
  //   permanent(400 ok:false !transient) → mark "failed" (needs manual retry/discard)
  //   transient(0 / 5xx / unparseable)   → keep, bump attempts, try again later
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
    }, Promise.resolve()).then(
      function () { flushing = false; if (window.inride.outboxUI) window.inride.outboxUI.refresh(); },
      function () { flushing = false; } // never leave the guard stuck on an unexpected throw
    );
  }

  // Replaced below (on-load section) with the real interval starter. Declared here so the
  // capture flows can call it before that definition is reached at module-eval time.
  let startOutboxTimer = function () {};

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
    startOutboxTimer();
    if (navigator.onLine === false) journeyUI.toast("Saved — will upload when you're back online.");
    journeyFlow.whatsNext(dest);
    flushOutbox();
  }

  // ── journeyFlow ──────────────────────────────────────────────────────────────
  const journeyFlow = {};

  // Soft login gate: logged-in users go straight to start; anonymous users see a
  // prompt so they can choose to log in (and preserve the chosen spot across the
  // redirect) or carry on without an account. No hard block — anonymous is fine.
  journeyFlow.startFromChoose = function (latlng) {
    if (window.IS_LOGGED_IN) return journeyFlow.beginWithCoHitchers(latlng);
    journeyUI.dialog({
      title: "Track your rides?",
      body: "Log in to keep your ride history, or just continue anonymously.",
      centered: true,
      actions: [
        {
          label: "Log in",
          cls: "inr-go",
          onClick: () => {
            // Stash the chosen pickup so we can resume after the redirect back.
            localStorage.setItem(PENDING_KEY, JSON.stringify({ lat: latlng.lat, lon: latlng.lng }));
            window.location.href = "/login?next=/";
          },
        },
        { label: "Continue anonymously", cls: "inr-grey", onClick: () => journeyFlow.beginWithCoHitchers(latlng) },
      ],
    });
  };

  // Bank the running wait segment and freeze the timer — paused time is never
  // counted toward the recorded wait. State transitions: waiting → paused.
  journeyFlow.pause = function () {
    const j = journeyStore.get(); if (!j || j.state !== "waiting") return;
    // Bank the active segment and stop the clock so a break/overnight is excluded.
    j.waitAccumMs = journeyStore.currentWaitMs(j, Date.now());
    j.waitSegmentStartMs = null; j.state = "paused";
    journeyUI.render(journeyStore.set(j));
  };

  // Restart the wait segment from now — continues from where it froze. State: paused → waiting.
  journeyFlow.resume = function () {
    const j = journeyStore.get(); if (!j || j.state !== "paused") return;
    j.waitSegmentStartMs = Date.now(); j.state = "waiting";
    journeyUI.render(journeyStore.set(j));
  };

  // Seed the waiting journey. Pickup = the chosen latlng; wait timer starts now.
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

  // Show the co-hitcher modal, then seed the journey with whoever was added.
  journeyFlow.beginWithCoHitchers = function (latlng) {
    journeyUI.coHitcherSheet(function (coHitchhikers) {
      journeyFlow.start(latlng, coHitchhikers);
    });
  };

  // Cancel the whole journey WITHOUT logging anything — for a journey started by mistake.
  // Distinct from Give Up (which records a rated spot experience); this just discards, so
  // it confirms first to avoid throwing away a real wait accidentally.
  journeyFlow.cancel = function () {
    if (!journeyStore.get()) return;
    if (!window.confirm("Cancel this journey? Your wait won't be saved.")) return;
    journeyStore.clear();
    journeyUI.teardown();
  };

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
        body: window.RideSubmit.buildGiveUpBody(j, waitMin, details, id),
      });
      journeyStore.clear();
      journeyUI.teardown();
      if (window.inride.outboxUI) window.inride.outboxUI.refresh();
      startOutboxTimer();
      if (navigator.onLine === false) journeyUI.toast("Saved — will upload when you're back online.");
      flushOutbox();
    });
  };

  // Boarded: departure time = now, wait is frozen (pause-aware), ride details are
  // captured; submission is deferred to Finish Ride (destination not known yet).
  journeyFlow.gotRide = function (details) {
    const j = journeyStore.get(); if (!j || (j.state !== "waiting")) return;
    j.gotRideMs = Date.now();
    j.finalWaitMs = journeyStore.currentWaitMs(j, j.gotRideMs);
    j.details = details; // {rating, vehicle_kind, signal:[...], comment}
    j.state = "in-ride";
    journeyUI.render(journeyStore.set(j));
  };

  // Capture the destination, submit the ride, then hand off to whatsNext.
  // GPS is tried first (up to 3 attempts); PERMISSION_DENIED or exhausted retries
  // fall back to a manual pin so Finish is never a dead end.
  journeyFlow.finish = function () {
    const j = journeyStore.get(); if (!j || j.state !== "in-ride") return;
    // A pin picker is already open (e.g. Finish tapped again) — don't re-run GPS / stack.
    if (journeyUI._picking) return;
    // Capture arrival time NOW, before GPS fix or manual-pin delay can inflate it.
    // The backend asserts arrival > departure; stamping here rather than at submit
    // prevents same-minute rides yielding arrival == departure → 400 → stuck retry.
    const finishMs = Date.now();
    // Confirm the drop-off location FIRST, then ask the would-ride-again question, then
    // submit. Re-read the journey so any details just added via the nudge are captured.
    // finishMs was stamped above, so the extra prompt delay never inflates arrival time.
    const proceedToGate = function () {
      const jj = journeyStore.get(); if (!jj) return;
      // Step 2 (after the location is confirmed): the forced would-ride-again answer,
      // then the actual ~5 s Nostr submit.
      const askAndSubmit = function (dest) {
        journeyUI.wouldRideAgainSheet(function (wouldRideAgain) {
          jj.wouldRideAgain = wouldRideAgain;
          journeyStore.set(jj);
          journeyUI.setFinishBusy(true); // Nostr publish takes ~5 s
          completeFinish(jj, dest, finishMs);
        });
      };
      // Step 1: confirm the destination — GPS (up to 3 tries), falling back to a manual
      // pin. Lock the button while GPS resolves; clear it before either prompt so the
      // user isn't staring at a spinner while answering.
      journeyUI.setFinishBusy(true);
      getFixWithRetry().then(
        function (dest) { journeyUI.setFinishBusy(false); askAndSubmit(dest); },
        function () {
          journeyUI.setFinishBusy(false);
          journeyUI.manualPin(function (dest) { askAndSubmit(dest); });
        }
      );
    };
    // Nudge to enrich the log before saving — but only when details are incomplete.
    // "Add details" saves onto j.details then proceeds; "Skip" proceeds as-is.
    const score = demographicScores(j.details || {});
    if (score.pct >= 100) { proceedToGate(); return; }
    journeyUI.finishNudge(
      score.pct,
      j.details || {},
      function (fields) {
        const cur = journeyStore.get(); if (cur) { cur.details = Object.assign({}, cur.details, fields); journeyStore.set(cur); }
        proceedToGate();
      },
      proceedToGate
    );
  };

  // After a ride is saved, ask whether to start another leg or call it a day.
  journeyFlow.whatsNext = function (dropoff) {
    // Clear the in-ride dock, chip, pickup pin, and tick interval so they don't
    // show through behind the dialog. State remains in-ride in the store until
    // nextRide (which calls render) or end (which calls teardown again harmlessly).
    journeyUI.teardown();
    journeyUI.dialog({
      title: "What's next?",
      body: "Ride saved — dropped off here. Waiting for another ride from this spot?",
      actions: [
        { label: "Next Ride", cls: "inr-go",   onClick: () => journeyUI.setWaitingSpot(dropoff, journeyFlow.nextRide, () => journeyFlow.whatsNext(dropoff)) },
        { label: "End Hitch", cls: "inr-grey",  onClick: () => journeyFlow.end() },
      ],
    });
  };

  // End the journey: wipe stored state and remove all journey chrome.
  journeyFlow.end = function () { journeyStore.clear(); journeyUI.teardown(); };

  // New leg: drop-off is the DEFAULT waiting location but the user can move it
  // (dropped at an exit, walks to a better spot). Fresh timers; pickup = confirmed pt.
  // latlng is a Leaflet LatLng (has .lat / .lng) — delivered by setWaitingSpot's Confirm.
  journeyFlow.nextRide = function (latlng) {
    const prev = journeyStore.get();
    const j = journeyStore.set({
      state: "waiting", pickup: { lat: latlng.lat, lon: latlng.lng },
      waitAccumMs: 0, waitSegmentStartMs: Date.now(),
      gotRideMs: null, finalWaitMs: null, details: null,
      legIndex: (prev && prev.legIndex || 0) + 1,
      coHitchhikers: (prev && prev.coHitchhikers) || [],
    });
    journeyUI.render(j);
  };

  // ── journeyUI ────────────────────────────────────────────────────────────────
  // Renders a scrim + bottom card mirroring .location-selection-ui.
  // Returns a close handle { close() } so callers can dismiss programmatically.
  const journeyUI = {
    _openDialog: null,   // guard: only one dialog open at a time (see Task-3 note)
    _picking: false,     // guard: a pin picker (manualPin) is open — don't stack another
    _setPin: null,       // while picking: (latlng) => reposition the destination pin (long-press)
    _tickInterval: null, // 1-s live-timer interval; at most one running at a time
    _dockEl: null,       // the persistent docked action bar
    _chipEl: null,       // the status chip above the dock
    _finishBtn: null,    // the Finish Ride button (for setFinishBusy)
    _pickupPin: null,    // Leaflet marker at the pickup location (in-ride state)

    // Remove all journey chrome and stop the live timer.
    teardown() {
      if (journeyUI._tickInterval) {
        clearInterval(journeyUI._tickInterval);
        journeyUI._tickInterval = null;
      }
      [journeyUI._dockEl, journeyUI._chipEl].forEach((el) => {
        if (el && el.parentNode) el.parentNode.removeChild(el);
      });
      journeyUI._dockEl = null;
      journeyUI._chipEl = null;
      // Remove the pickup pin placed during the in-ride state.
      if (journeyUI._pickupPin && window.map) {
        window.map.removeLayer(journeyUI._pickupPin);
      }
      journeyUI._pickupPin = null;
      journeyUI._finishBtn = null;
      document.body.classList.remove("inride-active");
    },

    // Single entry point for all journey-state rendering.
    // Always tears down first so re-renders (state changes, reloads) start clean.
    render(j) {
      journeyUI.teardown();
      if (!j) return;

      // Mark the body so CSS lifts the whole bottom-right control stack (locate, mode
      // switcher, zoom) above the dock + chip — the stock controls keep their normal
      // layout (no cover-flow takeover), just shifted up so +/- clear the buttons.
      document.body.classList.add("inride-active");

      switch (j.state) {
        case "waiting":
          journeyUI._renderWaiting(j);
          break;
        case "paused":
          journeyUI._renderPaused(j);
          break;
        case "in-ride":
          journeyUI._renderInRide(j);
          break;
        default:
          console.log("[inride] render: unknown state", j.state);
      }

      // Every state built its dock/chip above; seal both so taps on their buttons
      // never fall through to the map and open the spot underneath.
      sealTaps(journeyUI._dockEl);
      sealTaps(journeyUI._chipEl);
    },

    // Build the waiting dock bar + live-timer chip.
    _renderWaiting(j) {
      // ── Status chip ────────────────────────────────────────────────────────
      // Chip value derives from stored timestamps via currentWaitMs — never a
      // free-running counter — so reloads and pauses both stay exact.
      const chip = document.createElement("div");
      chip.className = "inr-chip inr-chip--wait";

      const dot = document.createElement("span");
      dot.className = "inr-chip__dot";
      chip.appendChild(dot);

      const label = document.createElement("span");
      label.className = "inr-chip__label";
      label.textContent = "Waiting · " + fmtHMS(journeyStore.currentWaitMs(j, Date.now()));
      chip.appendChild(label);

      // Pause pill: wired defensively — journeyFlow.pause is implemented in Task 6;
      // tapping is a no-op until that task lands.
      const pauseBtn = document.createElement("button");
      pauseBtn.className = "inr-pausepill";
      pauseBtn.innerHTML = '<i class="fa-solid fa-pause"></i> Pause';
      pauseBtn.addEventListener("click", function () {
        journeyFlow.pause && journeyFlow.pause();
      });
      chip.appendChild(pauseBtn);

      document.body.appendChild(chip);
      journeyUI._chipEl = chip;

      // 1-second tick: re-reads authoritative stored timestamps each tick so the
      // display stays correct across tab switches, device sleep, and future pauses.
      journeyUI._tickInterval = setInterval(function () {
        const cur = journeyStore.get();
        label.textContent = "Waiting · " + fmtHMS(journeyStore.currentWaitMs(cur, Date.now()));
      }, 1000);

      // ── Docked action bar (button row + a small grey Cancel beneath) ─────────
      const dock = document.createElement("div");
      dock.className = "inr-dock inr-dock--stack";

      const row = document.createElement("div");
      row.className = "inr-dock-row";

      // Give Up (red) — logs a rated spot experience for the wait.
      const giveUpBtn = document.createElement("button");
      giveUpBtn.className = "inr-big inr-big--red";
      giveUpBtn.innerHTML = '<i class="fa-solid fa-flag"></i> Give Up';
      giveUpBtn.addEventListener("click", function () {
        journeyFlow.giveUp && journeyFlow.giveUp();
      });
      row.appendChild(giveUpBtn);

      // Got a Ride! (green) — opens the ride-details sheet; sheet's Ride On! calls gotRide.
      const gotRideBtn = document.createElement("button");
      gotRideBtn.className = "inr-big inr-big--green";
      gotRideBtn.innerHTML = '<i class="fa-solid fa-thumbs-up"></i> Got a Ride!';
      gotRideBtn.addEventListener("click", function () {
        // Open the slim sheet to capture rating/details; gotRide is called on Ride On!.
        journeyUI.rideDetailsSheet(function (details) {
          journeyFlow.gotRide(details);
        });
      });
      row.appendChild(gotRideBtn);
      dock.appendChild(row);
      dock.appendChild(journeyUI._cancelButton());

      document.body.appendChild(dock);
      journeyUI._dockEl = dock;

      // Show grey pickup pin so the user sees their waiting spot on the map.
      // Also drawn in paused and in-ride so the boarding spot is always visible.
      journeyUI._addPickupPin(j);
    },

    // Round red "cancel" button (white × in a red circle) centered beneath the dock —
    // discards the journey (confirmed) for a mistaken start, without logging anything.
    _cancelButton() {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "inr-cancel";
      btn.setAttribute("aria-label", "Cancel journey");
      btn.innerHTML = '<i class="fa-solid fa-xmark" aria-hidden="true"></i>';
      btn.addEventListener("click", function () { journeyFlow.cancel(); });
      return btn;
    },

    // Build the paused dock bar + frozen chip (mirrors waiting but timer is frozen
    // and Got a Ride! is disabled — resume first before claiming a ride).
    _renderPaused(j) {
      // ── Status chip (FROZEN — no tick interval while paused) ────────────────
      // Shows the banked accumulator only; the null segment contributes zero.
      const chip = document.createElement("div");
      chip.className = "inr-chip inr-chip--paused";

      const dot = document.createElement("span");
      dot.className = "inr-chip__dot";
      chip.appendChild(dot);

      const label = document.createElement("span");
      label.className = "inr-chip__label";
      // waitSegmentStartMs is null so currentWaitMs equals waitAccumMs — display is frozen.
      label.textContent = "Paused · waited " + fmtHMS(journeyStore.currentWaitMs(j, Date.now()));
      chip.appendChild(label);

      // Resume pill: restarts the wait segment from now.
      const resumeBtn = document.createElement("button");
      resumeBtn.className = "inr-pausepill";
      resumeBtn.innerHTML = '<i class="fa-solid fa-play"></i> Resume';
      resumeBtn.addEventListener("click", function () {
        journeyFlow.resume();
      });
      chip.appendChild(resumeBtn);

      document.body.appendChild(chip);
      journeyUI._chipEl = chip;

      // ── Docked action bar (button row + a small grey Cancel beneath) ─────────
      const dock = document.createElement("div");
      dock.className = "inr-dock inr-dock--stack";

      const row = document.createElement("div");
      row.className = "inr-dock-row";

      // Give Up (red) — active even while paused.
      const giveUpBtn = document.createElement("button");
      giveUpBtn.className = "inr-big inr-big--red";
      giveUpBtn.innerHTML = '<i class="fa-solid fa-flag"></i> Give Up';
      giveUpBtn.addEventListener("click", function () {
        journeyFlow.giveUp && journeyFlow.giveUp();
      });
      row.appendChild(giveUpBtn);

      // Got a Ride! — disabled while paused so accidental taps can't cut the wait short.
      const gotRideBtn = document.createElement("button");
      gotRideBtn.className = "inr-big inr-big--green inr-disabled";
      gotRideBtn.disabled = true;
      gotRideBtn.innerHTML = '<i class="fa-solid fa-thumbs-up"></i> Got a Ride!';
      row.appendChild(gotRideBtn);
      dock.appendChild(row);
      dock.appendChild(journeyUI._cancelButton());

      document.body.appendChild(dock);
      journeyUI._dockEl = dock;

      // Grey pickup pin — redrawn in waiting/paused/in-ride so the boarding spot
      // stays visible in all live journey states.
      journeyUI._addPickupPin(j);
    },

    // Build the in-ride dock bar + elapsed-time chip + grey pickup pin.
    _renderInRide(j) {
      // ── Status chip: live elapsed time since boarding ──────────────────────
      // Counts up from gotRideMs (not the wait timer); a 1-s tick re-reads the
      // stored timestamp so backgrounded tabs stay accurate after resume.
      const chip = document.createElement("div");
      chip.className = "inr-chip inr-chip--inride";

      const dot = document.createElement("span");
      dot.className = "inr-chip__dot";
      chip.appendChild(dot);

      const label = document.createElement("span");
      label.className = "inr-chip__label";
      label.textContent = "In a ride · " + fmtHMS(Date.now() - j.gotRideMs);
      chip.appendChild(label);

      document.body.appendChild(chip);
      journeyUI._chipEl = chip;

      journeyUI._tickInterval = setInterval(function () {
        const cur = journeyStore.get();
        if (cur && cur.gotRideMs) {
          label.textContent = "In a ride · " + fmtHMS(Date.now() - cur.gotRideMs);
        }
      }, 1000);

      // ── Grey pickup pin: marks the boarding spot while in-ride ────────────
      // Factored into _addPickupPin (also called from waiting/paused) so the pin
      // is always visible regardless of which live state the journey is in.
      journeyUI._addPickupPin(j);

      // ── Docked action bar: Finish Ride button + round red Cancel beneath ────
      // Stacked layout (like waiting/paused) so the round red Cancel × can sit
      // centered beneath the action row — the escape hatch stays available all the
      // way through Finish, so a journey can always be discarded without logging.
      const dock = document.createElement("div");
      dock.className = "inr-dock inr-dock--stack";

      const row = document.createElement("div");
      row.className = "inr-dock-row";

      // Orange (#ff6b35) signals a transitional/completion action — distinct from
      // the permanent red "Give Up" or confirming green "Got a Ride!".
      const finishBtn = document.createElement("button");
      finishBtn.className = "inr-big";
      finishBtn.style.background = "#ff6b35";
      finishBtn.innerHTML = '<i class="fa-solid fa-flag-checkered"></i> Finish Ride';
      finishBtn.addEventListener("click", function () {
        journeyFlow.finish && journeyFlow.finish();
      });
      row.appendChild(finishBtn);
      journeyUI._finishBtn = finishBtn;

      // Demographic entry during the ride: ONE chip that both shows the combined
      // completeness and opens the details sheet. Save merges onto j.details (submitted
      // at Finish). Sits on its own line above Finish in the stacked dock.
      const demoRow = document.createElement("div");
      demoRow.className = "inr-demo-row";
      const s = demographicScores(j.details || {});
      // Fill-bar chip: a blue fill on a black bar tracks completeness; the whole chip
      // is the tap target that opens the details sheet.
      const addBtn = document.createElement("button");
      addBtn.type = "button"; addBtn.className = "inr-demo-add";
      const addFill = document.createElement("span");
      addFill.className = "inr-demo-add__fill"; addFill.style.width = s.pct + "%";
      const addLabel = document.createElement("span");
      addLabel.className = "inr-demo-add__label";
      addLabel.innerHTML = s.pct >= 100
        ? '<i class="fa-solid fa-check"></i> Details complete'
        : '<i class="fa-solid fa-plus"></i> Add details · ' + s.pct + '%';
      addBtn.appendChild(addFill); addBtn.appendChild(addLabel);
      addBtn.addEventListener("click", function () {
        journeyUI.detailsSheet(j.details || {}, function (fields) {
          const cur = journeyStore.get(); if (!cur) return;
          cur.details = Object.assign({}, cur.details, fields);
          journeyStore.set(cur);
          journeyUI.render(cur); // re-render so the chip updates
        });
      });
      demoRow.appendChild(addBtn);
      // Insert ABOVE the Finish row (DOM order = top→bottom in the stacked dock).
      // Placed below, it wrapped onto the bottom edge and hid behind the nav / OSM credits.
      dock.appendChild(demoRow);
      dock.appendChild(row);
      // Round red Cancel × beneath the Finish button — same escape hatch as
      // waiting/paused, so the journey can be discarded at any point.
      dock.appendChild(journeyUI._cancelButton());

      document.body.appendChild(dock);
      journeyUI._dockEl = dock;
    },

    // Place (or replace) the grey pickup pin on the map.
    // Called from all three journey states so the boarding spot is always visible —
    // teardown() removes it between state transitions so pins don't stack.
    _addPickupPin(j) {
      if (window.L && window.map && j.pickup) {
        const greyIcon = L.icon({
          iconUrl: "/static/markers/marker-icon-2x-grey.png",
          shadowUrl: "/static/markers/marker-shadow.png",
          iconSize: [25, 41], iconAnchor: [12, 41],
          popupAnchor: [1, -34], shadowSize: [41, 41],
        });
        journeyUI._pickupPin = L.marker([j.pickup.lat, j.pickup.lon], { icon: greyIcon })
          .addTo(window.map);
      }
    },

    // Toggle the Finish Ride button's busy state during the ~5s Nostr publish.
    // Keeps the user from double-tapping while a submission is in flight.
    setFinishBusy(busy) {
      const btn = journeyUI._finishBtn;
      if (!btn) return;
      btn.disabled = busy;
      btn.classList.toggle("inr-disabled", busy);
      btn.innerHTML = busy
        ? '<i class="fa-solid fa-spinner fa-spin"></i> Saving…'
        : '<i class="fa-solid fa-flag-checkered"></i> Finish Ride';
    },

    // Brief error banner above the dock; auto-removes after 5 s so stale errors
    // don't linger. In-ride state is preserved so the user can retry.
    error(msg) {
      const existing = document.getElementById("inr-error-banner");
      if (existing && existing.parentNode) existing.parentNode.removeChild(existing);
      const banner = document.createElement("div");
      banner.id = "inr-error-banner";
      // Sit ABOVE the dock+chip stack (chip tops out at ~var+108px) and above their
      // z-index (2002), so the message is readable and never hidden behind the
      // Finish Ride button — the original 1300 rendered it behind the dock.
      banner.style.cssText = [
        "position:fixed", "left:10px", "right:10px",
        "bottom:calc(var(--bottom-pane-h, env(safe-area-inset-bottom,0px)) + 120px)",
        "background:#b00020", "color:#fff", "border-radius:12px",
        "padding:12px 16px", "font-size:14px", "font-weight:600",
        "z-index:2003", "text-align:center",
        "box-shadow:0 3px 10px rgba(0,0,0,.25)",
      ].join(";");
      banner.textContent = msg;
      document.body.appendChild(banner);
      setTimeout(function () {
        if (banner.parentNode) banner.parentNode.removeChild(banner);
      }, 5000);
    },

    // Brief, non-blocking confirmation (distinct from error()'s red banner). Used to tell
    // the user a ride was safely queued when they're offline. Auto-removes after 4 s.
    toast(msg) {
      const t = document.createElement("div");
      t.className = "inr-toast";
      t.textContent = msg;
      document.body.appendChild(t);
      setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 4000);
    },

    // Inline manual-pin fallback for destination selection.
    // We cannot reuse setupLocationSelection() here because its confirmLocationSelection()
    // writes to sessionStorage and then does window.location.href = "/ride" — a redirect
    // that would exit the in-ride flow entirely. Instead we build a minimal pin-selection
    // UI directly on the Leaflet map and hand the chosen latlng to the callback.
    manualPin(cb, seedLatLng) {
      if (!window.L || !window.map) {
        // No map available (edge case) — reset busy so the user isn't stuck.
        journeyUI.setFinishBusy(false);
        return;
      }
      // Never stack two pin pickers: a second card would reuse the same button ids and
      // steal the first card's Confirm/Cancel wiring, leaving the visible buttons dead.
      if (journeyUI._picking) return;
      journeyUI._picking = true;

      // Leaflet LatLng exposes .lat and .lng (not .lon). buildFinishBody reads dest.lon,
      // so we normalize .lng → .lon when reading the marker position; passing a raw
      // Leaflet LatLng would leave destination_lon=undefined and the backend would
      // reject the submission without a clear error.
      // seedLatLng (optional) pre-places the pin; defaults to the current map centre.
      const marker = L.marker(seedLatLng || window.map.getCenter(), {
        draggable: true,
        icon: L.icon({
          iconUrl: "/static/markers/marker-icon-2x-orange.png",
          shadowUrl: "/static/markers/marker-shadow.png",
          iconSize: [25, 41], iconAnchor: [12, 41],
          popupAnchor: [1, -34], shadowSize: [41, 41],
        }),
      }).addTo(window.map);

      // Tapping the map also repositions the destination pin (same UX as the
      // standard location-selection UI in map.js).
      function onMapClick(e) { marker.setLatLng(e.latlng); }
      window.map.on("click", onMapClick);

      // Expose a reposition hook so a long-press (routed through inrideOnEntryGesture)
      // can drop the pin too — but ONLY while this picker is open, so long-press never
      // drops a pin before the user has entered the Finish flow.
      journeyUI._setPin = function (ll) { marker.setLatLng(ll); };

      const ui = document.createElement("div");
      ui.className = "location-selection-ui";
      ui.innerHTML = [
        "<h4>Drop a pin for your destination</h4>",
        "<p>Tap & drag the pin, then confirm.</p>",
        '<div class="lsel-actions">',
        '<button class="lsel-confirm" id="inr-pin-confirm">Confirm Destination</button>',
        '<button class="lsel-cancel" id="inr-pin-cancel">Cancel</button>',
        "</div>",
      ].join("");
      document.body.appendChild(ui);
      // While dropping the pin, neutralize overlay markers (e.g. Hitchwiki event
      // pins) so a stray tap on one repositions the pin instead of opening its
      // sheet and swallowing the click. See body.inr-picking rule in style.css.
      document.body.classList.add("inr-picking");

      function cleanup() {
        window.map.removeLayer(marker);
        window.map.off("click", onMapClick);
        document.body.classList.remove("inr-picking");
        journeyUI._picking = false;
        journeyUI._setPin = null;
        if (ui.parentNode) ui.parentNode.removeChild(ui);
      }

      document.getElementById("inr-pin-confirm").addEventListener("click", function () {
        const ll = marker.getLatLng();
        cleanup();
        // Normalize Leaflet's .lng → .lon so buildFinishBody receives the correct longitude.
        cb({ lat: ll.lat, lon: ll.lng });
      });

      document.getElementById("inr-pin-cancel").addEventListener("click", function () {
        cleanup();
        // User dismissed the pin — stay in in-ride state with busy cleared (retry possible).
        journeyUI.setFinishBusy(false);
      });
    },

    // ── Slim "How was the spot?" bottom sheet ──────────────────────────────────
    // Opens over the scrim. onSave({ rating, vehicle_kind, signal:[...], comment })
    // is called when the user taps "Ride On!" (requires a rating to enable).
    // Signal codes match ride_form.html datalist: thumb / sign / ask.
    // Vehicle kind codes match KindEnum: car / truck / van.
    rideDetailsSheet(onSave) {
      // Close any already-open dialog so we can't stack overlays.
      if (journeyUI._openDialog) journeyUI._openDialog.close();

      const scrim = document.createElement("div");
      scrim.className = "inride-scrim";

      const sheet = document.createElement("div");
      sheet.className = "inr-sheet";

      // Drag handle visual cue
      const grab = document.createElement("div");
      grab.className = "inr-sheet__grab";
      sheet.appendChild(grab);

      // Explicit close so the user isn't forced to create a ride just because the sheet
      // opened — dismisses without onSave, leaving the journey in its current (waiting) state.
      const closeX = document.createElement("button");
      closeX.type = "button";
      closeX.className = "inr-sheet__close";
      closeX.setAttribute("aria-label", "Close");
      closeX.innerHTML = "&times;";
      closeX.addEventListener("click", function () { close(); });
      sheet.appendChild(closeX);

      // Title
      const titleEl = document.createElement("h4");
      titleEl.textContent = "How was the spot?";
      sheet.appendChild(titleEl);

      // ── 5-star rating (required — Ride On! stays disabled until a star is tapped) ──
      let rating = 0;
      const starsEl = document.createElement("div");
      starsEl.className = "inr-stars";
      const starEls = [];
      for (let i = 1; i <= 5; i++) {
        const star = document.createElement("span");
        star.className = "inr-star";
        star.setAttribute("data-value", String(i));
        star.textContent = "★";
        star.addEventListener("click", (function (val) {
          return function () { rating = val; updateStars(); updateRideOnBtn(); };
        }(i)));
        starsEl.appendChild(star);
        starEls.push(star);
      }
      function updateStars() {
        starEls.forEach(function (s, idx) {
          s.classList.toggle("inr-star--on", idx < rating);
        });
      }
      sheet.appendChild(starsEl);

      // ── Vehicle-kind chips: single-select, default = car ──────────────────────
      let vehicleKind = "car";
      const vehicleField = document.createElement("div");
      vehicleField.className = "inr-field";
      const vehicleLabel = document.createElement("label");
      vehicleLabel.textContent = "Who picked you up?";
      vehicleField.appendChild(vehicleLabel);
      const vehicleChipsEl = document.createElement("div");
      vehicleChipsEl.className = "inr-chips";
      [
        { code: "car",   label: "🚗 Car"   },
        { code: "truck", label: "🚚 Truck" },
        { code: "van",   label: "🚐 Van"   },
      ].forEach(function (opt) {
        const chip = document.createElement("button");
        chip.type = "button";
        // inr-optchip (not inr-chip) avoids the CSS collision with the fixed status
        // pill — both are bare selectors of equal specificity and would merge otherwise.
        chip.className = "inr-optchip" + (opt.code === "car" ? " inr-optchip--on" : "");
        chip.textContent = opt.label;
        chip.setAttribute("data-code", opt.code);
        chip.addEventListener("click", function () {
          vehicleKind = opt.code;
          // Single-select: deactivate siblings, activate tapped chip.
          vehicleChipsEl.querySelectorAll(".inr-optchip").forEach(function (c) {
            c.classList.toggle("inr-optchip--on", c.getAttribute("data-code") === vehicleKind);
          });
        });
        vehicleChipsEl.appendChild(chip);
      });
      vehicleField.appendChild(vehicleChipsEl);
      sheet.appendChild(vehicleField);

      // ── Signal chips: multi-select (array of codes sent to /ride) ─────────────
      // Codes verified against ride_form.html datalist: thumb / sign / ask.
      const signals = new Set();
      const signalField = document.createElement("div");
      signalField.className = "inr-field";
      const signalLabel = document.createElement("label");
      signalLabel.textContent = "How did you signal?";
      signalField.appendChild(signalLabel);
      const signalChipsEl = document.createElement("div");
      signalChipsEl.className = "inr-chips";
      [
        { code: "thumb", label: "👍 Thumb"  },
        { code: "sign",  label: "📝 Sign"   },
        { code: "ask",   label: "🗣 Asking" },
      ].forEach(function (opt) {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "inr-optchip"; // inr-optchip: distinct from status-pill .inr-chip
        chip.textContent = opt.label;
        chip.setAttribute("data-code", opt.code);
        chip.addEventListener("click", function () {
          // Toggle: each signal method can be selected independently.
          if (signals.has(opt.code)) { signals.delete(opt.code); chip.classList.remove("inr-optchip--on"); }
          else { signals.add(opt.code); chip.classList.add("inr-optchip--on"); }
        });
        signalChipsEl.appendChild(chip);
      });
      signalField.appendChild(signalChipsEl);
      sheet.appendChild(signalField);

      // ── Optional comment ───────────────────────────────────────────────────────
      const commentField = document.createElement("div");
      commentField.className = "inr-field";
      const commentLabel = document.createElement("label");
      commentLabel.textContent = "Comment (optional)";
      commentField.appendChild(commentLabel);
      const textarea = document.createElement("textarea");
      textarea.className = "inr-sheet__textarea";
      textarea.placeholder = "Anything worth noting about this spot…";
      commentField.appendChild(textarea);
      sheet.appendChild(commentField);

      // ── Ride On! CTA (green, disabled until rating chosen) ────────────────────
      const rideOnBtn = document.createElement("button");
      rideOnBtn.type = "button";
      rideOnBtn.className = "inr-big inr-big--green inr-sheet__save inr-disabled";
      rideOnBtn.disabled = true;
      rideOnBtn.innerHTML = '<i class="fa-solid fa-check"></i> Ride On!';
      function updateRideOnBtn() {
        const ready = rating > 0;
        rideOnBtn.disabled = !ready;
        rideOnBtn.classList.toggle("inr-disabled", !ready);
      }
      rideOnBtn.addEventListener("click", function () {
        if (!rating) return; // guard: button should be disabled, but double-check
        const details = {
          rating: rating,
          vehicle_kind: vehicleKind,
          signal: Array.from(signals),
          comment: textarea.value.trim(),
        };
        close();
        onSave(details);
      });
      sheet.appendChild(rideOnBtn);

      function close() {
        if (scrim.parentNode) scrim.parentNode.removeChild(scrim);
        if (sheet.parentNode) sheet.parentNode.removeChild(sheet);
        journeyUI._openDialog = null;
      }

      // Scrim tap (outside the sheet) dismisses without saving.
      scrim.addEventListener("click", close);

      document.body.appendChild(scrim);
      document.body.appendChild(sheet);
      journeyUI._openDialog = { close };
      return { close };
    },

    // In-ride driver/vehicle detail entry with two live completeness meters. Seeded
    // from the current details; onSave(fields) fires on Save with the canonical field
    // names. NOT a submission — the caller merges the result onto the journey.
    detailsSheet(seed, onSave) {
      if (journeyUI._openDialog) journeyUI._openDialog.close();
      const ch = _choices || { reasons: [], genders: [], languages: [], countries: [], plate_countries: [], vehicle_kinds: [], passenger_kinds: [] };
      // Working copy of the fields, seeded from `seed`.
      const f = {
        driver_reason_to_pick_up: (seed.driver_reason_to_pick_up || []).slice(),
        driver_gender: seed.driver_gender || "",
        driver_age: (seed.driver_age === 0 || seed.driver_age) ? seed.driver_age : "",
        driver_origin_country: seed.driver_origin_country || "",
        driver_languages: (seed.driver_languages || []).slice(),
        vehicle_kind: seed.vehicle_kind || "",
        vehicle_license_plate_country: seed.vehicle_license_plate_country || "",
        vehicle_make: seed.vehicle_make || "",
        vehicle_model: seed.vehicle_model || "",
      };

      const scrim = document.createElement("div");
      scrim.className = "inride-scrim";
      const sheet = document.createElement("div");
      sheet.className = "inr-sheet inr-sheet--scroll";

      const grab = document.createElement("div"); grab.className = "inr-sheet__grab"; sheet.appendChild(grab);
      const closeX = document.createElement("button");
      closeX.type = "button"; closeX.className = "inr-sheet__close"; closeX.setAttribute("aria-label", "Close");
      closeX.innerHTML = "&times;"; closeX.addEventListener("click", function () { close(); });
      sheet.appendChild(closeX);

      const titleEl = document.createElement("h4"); titleEl.textContent = "Driver & vehicle details"; sheet.appendChild(titleEl);

      // ── Two tabs (Driver / Vehicle), each a fill-bar of its own section's
      //    completeness. Only the active panel shows; the fill bars update live. ──
      const tabbar = document.createElement("div"); tabbar.className = "inr-tabbar";
      const driverPanel = document.createElement("div"); driverPanel.className = "inr-tabpanel";
      const vehiclePanel = document.createElement("div"); vehiclePanel.className = "inr-tabpanel";
      const driverTab = makeTab("Driver"); const vehicleTab = makeTab("Vehicle");
      tabbar.appendChild(driverTab.el); tabbar.appendChild(vehicleTab.el);
      sheet.appendChild(tabbar); sheet.appendChild(driverPanel); sheet.appendChild(vehiclePanel);

      function showTab(which) {
        const onDriver = which === "driver";
        driverPanel.style.display = onDriver ? "" : "none";
        vehiclePanel.style.display = onDriver ? "none" : "";
        driverTab.el.classList.toggle("inr-tab--on", onDriver);
        vehicleTab.el.classList.toggle("inr-tab--on", !onDriver);
      }
      driverTab.el.addEventListener("click", function () { showTab("driver"); });
      vehicleTab.el.addEventListener("click", function () { showTab("vehicle"); });

      function refreshMeters() {
        const s = demographicScores(f);
        driverTab.set(s.driver.pct); vehicleTab.set(s.vehicle.pct);
        makeModelWrap.style.display = (ch.passenger_kinds.indexOf(f.vehicle_kind) !== -1) ? "" : "none";
      }
      // A tab is a button: label + its section's % on top, a thin fill bar beneath.
      function makeTab(label) {
        const el = document.createElement("button"); el.type = "button"; el.className = "inr-tab";
        const top = document.createElement("span"); top.className = "inr-tab__top";
        const l = document.createElement("span"); l.className = "inr-tab__label"; l.textContent = label;
        const pct = document.createElement("span"); pct.className = "inr-tab__pct";
        top.appendChild(l); top.appendChild(pct);
        const track = document.createElement("span"); track.className = "inr-tab__track";
        const fill = document.createElement("span"); fill.className = "inr-tab__fill"; track.appendChild(fill);
        el.appendChild(top); el.appendChild(track);
        return { el: el, set: function (p) { fill.style.width = p + "%"; pct.textContent = p + "%"; } };
      }

      // ── Field builders (chips single/multi, stepper, searchable select) ──────
      function fieldWrap(labelText) {
        const w = document.createElement("div"); w.className = "inr-field";
        const l = document.createElement("label"); l.textContent = labelText; w.appendChild(l);
        return w;
      }
      // Single-select chips (gender). choices: [[code,label],…]
      function chipSingle(w, choices, getVal, setVal) {
        const row = document.createElement("div"); row.className = "inr-chips";
        choices.forEach(function (pair) {
          const b = document.createElement("button"); b.type = "button"; b.className = "inr-optchip";
          b.textContent = pair[1]; b.setAttribute("data-code", pair[0]);
          if (getVal() === pair[0]) b.classList.add("inr-optchip--on");
          b.addEventListener("click", function () {
            setVal(getVal() === pair[0] ? "" : pair[0]); // tap again clears
            row.querySelectorAll(".inr-optchip").forEach(function (c) {
              c.classList.toggle("inr-optchip--on", c.getAttribute("data-code") === getVal());
            });
            refreshMeters();
          });
          row.appendChild(b);
        });
        w.appendChild(row);
      }
      // Multi-select chips (reasons, languages). arr is the working array of codes.
      function chipMulti(w, choices, arr) {
        const row = document.createElement("div"); row.className = "inr-chips";
        choices.forEach(function (pair) {
          const b = document.createElement("button"); b.type = "button"; b.className = "inr-optchip"; b.textContent = pair[1];
          if (arr.indexOf(pair[0]) !== -1) b.classList.add("inr-optchip--on");
          b.addEventListener("click", function () {
            const i = arr.indexOf(pair[0]);
            if (i === -1) { arr.push(pair[0]); b.classList.add("inr-optchip--on"); }
            else { arr.splice(i, 1); b.classList.remove("inr-optchip--on"); }
            refreshMeters();
          });
          row.appendChild(b);
        });
        w.appendChild(row);
      }
      // Searchable select for long lists (country, plate country). choices pairs [code,name].
      function searchSelect(w, choices, placeholder, getVal, setVal) {
        const input = document.createElement("input"); input.type = "text"; input.className = "inr-cohitch-input";
        input.placeholder = placeholder; input.setAttribute("autocomplete", "off");
        const cur = choices.find(function (p) { return p[0] === getVal(); });
        if (cur) input.value = cur[1];
        const list = document.createElement("ul"); list.className = "inr-cohitch-suggest"; list.style.display = "none";
        const wrap = document.createElement("div"); wrap.className = "inr-cohitch-inputwrap";
        wrap.appendChild(input); wrap.appendChild(list); w.appendChild(wrap);
        input.addEventListener("input", function () {
          const q = input.value.trim().toLowerCase();
          list.innerHTML = "";
          if (!q) { list.style.display = "none"; setVal(""); refreshMeters(); return; }
          choices.filter(function (p) { return p[1].toLowerCase().indexOf(q) !== -1; }).slice(0, 8).forEach(function (p) {
            const li = document.createElement("li"); li.textContent = p[1];
            li.addEventListener("mousedown", function (e) { e.preventDefault(); input.value = p[1]; setVal(p[0]); list.style.display = "none"; refreshMeters(); });
            list.appendChild(li);
          });
          list.style.display = list.children.length ? "block" : "none";
        });
      }

      // Number-plate country: search by the code shown on the plate (e.g. "D", "F",
      // "GB") OR the country name, matching the historic "log a past ride" form.
      // triples are [iso_alpha2, plate_code, name]; we store the ISO alpha-2.
      function plateSelect(w, triples, getVal, setVal) {
        const input = document.createElement("input"); input.type = "text"; input.className = "inr-cohitch-input";
        input.placeholder = "License plate code (e.g. D, F, GB)…"; input.setAttribute("autocomplete", "off");
        const cur = triples.find(function (t) { return t[0] === getVal(); });
        if (cur) input.value = cur[1];
        const list = document.createElement("ul"); list.className = "inr-cohitch-suggest"; list.style.display = "none";
        const wrap = document.createElement("div"); wrap.className = "inr-cohitch-inputwrap";
        wrap.appendChild(input); wrap.appendChild(list); w.appendChild(wrap);
        input.addEventListener("input", function () {
          const q = input.value.trim().toLowerCase();
          list.innerHTML = "";
          if (!q) { list.style.display = "none"; setVal(""); refreshMeters(); return; }
          triples.filter(function (t) { return t[1].toLowerCase().indexOf(q) !== -1 || t[2].toLowerCase().indexOf(q) !== -1; }).slice(0, 8).forEach(function (t) {
            const li = document.createElement("li"); li.textContent = t[1] + " — " + t[2];
            li.addEventListener("mousedown", function (e) { e.preventDefault(); input.value = t[1]; setVal(t[0]); list.style.display = "none"; refreshMeters(); });
            list.appendChild(li);
          });
          list.style.display = list.children.length ? "block" : "none";
        });
      }
      // Tag autocomplete (LinkedIn-skill style): type to search, tap a suggestion to add
      // it as a removable tag. arr is the working array of codes; already-added codes are
      // excluded from suggestions. choices are [code, name] pairs.
      function tagAutocomplete(w, choices, arr) {
        const wrap = document.createElement("div"); wrap.className = "inr-cohitch-inputwrap";
        const tags = document.createElement("div"); tags.className = "inr-tags";
        const input = document.createElement("input"); input.type = "text"; input.className = "inr-cohitch-input";
        input.placeholder = "Type a language…"; input.setAttribute("autocomplete", "off");
        const list = document.createElement("ul"); list.className = "inr-cohitch-suggest"; list.style.display = "none";
        wrap.appendChild(tags); wrap.appendChild(input); wrap.appendChild(list); w.appendChild(wrap);
        function nameFor(code) { const p = choices.find(function (c) { return c[0] === code; }); return p ? p[1] : code; }
        function renderTags() {
          tags.innerHTML = "";
          arr.forEach(function (code) {
            const t = document.createElement("span"); t.className = "inr-tag"; t.textContent = nameFor(code);
            const x = document.createElement("button"); x.type = "button"; x.className = "inr-tag__x"; x.setAttribute("aria-label", "Remove"); x.innerHTML = "&times;";
            x.addEventListener("click", function () { const i = arr.indexOf(code); if (i !== -1) arr.splice(i, 1); renderTags(); refreshMeters(); });
            t.appendChild(x); tags.appendChild(t);
          });
        }
        input.addEventListener("input", function () {
          const q = input.value.trim().toLowerCase();
          list.innerHTML = "";
          if (!q) { list.style.display = "none"; return; }
          choices.filter(function (p) { return arr.indexOf(p[0]) === -1 && p[1].toLowerCase().indexOf(q) !== -1; }).slice(0, 8).forEach(function (p) {
            const li = document.createElement("li"); li.textContent = p[1];
            li.addEventListener("mousedown", function (e) {
              e.preventDefault();
              if (arr.indexOf(p[0]) === -1) arr.push(p[0]);
              input.value = ""; list.style.display = "none"; renderTags(); refreshMeters();
            });
            list.appendChild(li);
          });
          list.style.display = list.children.length ? "block" : "none";
        });
        renderTags();
      }

      // ── Driver tab ───────────────────────────────────────────────────────────
      const reasonF = fieldWrap("Why did they pick you up?"); chipMulti(reasonF, ch.reasons, f.driver_reason_to_pick_up); driverPanel.appendChild(reasonF);
      const genderF = fieldWrap("Driver gender"); chipSingle(genderF, ch.genders, function () { return f.driver_gender; }, function (v) { f.driver_gender = v; }); driverPanel.appendChild(genderF);
      const ageF = fieldWrap("Approx. driver age");
      const ageHelp = document.createElement("div"); ageHelp.className = "inr-field__help"; ageHelp.textContent = "A rough guess is fine."; ageF.appendChild(ageHelp);
      const age = document.createElement("input"); age.type = "number"; age.min = "0"; age.max = "120"; age.className = "inr-cohitch-input"; age.inputMode = "numeric";
      if (f.driver_age !== "") age.value = f.driver_age;
      age.addEventListener("input", function () { f.driver_age = age.value === "" ? "" : parseInt(age.value, 10); refreshMeters(); });
      ageF.appendChild(age); driverPanel.appendChild(ageF);
      const originF = fieldWrap("Driver's country"); searchSelect(originF, ch.countries, "Search country…", function () { return f.driver_origin_country; }, function (v) { f.driver_origin_country = v; }); driverPanel.appendChild(originF);
      const langF = fieldWrap("Languages spoken"); tagAutocomplete(langF, ch.languages, f.driver_languages); driverPanel.appendChild(langF);

      // ── Vehicle tab ──────────────────────────────────────────────────────────
      const kindF = fieldWrap("Vehicle");
      chipSingle(kindF, ch.vehicle_kinds.map(function (p) { return [p[0], p[1] + " " + p[0]]; }), function () { return f.vehicle_kind; }, function (v) { f.vehicle_kind = v; });
      vehiclePanel.appendChild(kindF);
      const plateF = fieldWrap("Number-plate country"); plateSelect(plateF, ch.plate_countries, function () { return f.vehicle_license_plate_country; }, function (v) { f.vehicle_license_plate_country = v; }); vehiclePanel.appendChild(plateF);
      // make/model — passenger vehicles only, optional (not scored). Hidden for other kinds by refreshMeters().
      const makeModelWrap = document.createElement("div");
      const makeF = fieldWrap("Make (optional)"); const make = document.createElement("input"); make.type = "text"; make.className = "inr-cohitch-input"; make.value = f.vehicle_make; make.addEventListener("input", function () { f.vehicle_make = make.value; refreshMeters(); }); makeF.appendChild(make); makeModelWrap.appendChild(makeF);
      const modelF = fieldWrap("Model (optional)"); const model = document.createElement("input"); model.type = "text"; model.className = "inr-cohitch-input"; model.value = f.vehicle_model; model.addEventListener("input", function () { f.vehicle_model = model.value; refreshMeters(); }); modelF.appendChild(model); makeModelWrap.appendChild(modelF);
      vehiclePanel.appendChild(makeModelWrap);

      const saveBtn = document.createElement("button");
      saveBtn.type = "button"; saveBtn.className = "inr-big inr-big--green inr-sheet__save";
      saveBtn.innerHTML = '<i class="fa-solid fa-check"></i> Save details';
      saveBtn.addEventListener("click", function () { close(); onSave(f); });
      sheet.appendChild(saveBtn);

      function close() {
        if (scrim.parentNode) scrim.parentNode.removeChild(scrim);
        if (sheet.parentNode) sheet.parentNode.removeChild(sheet);
        journeyUI._openDialog = null;
      }
      scrim.addEventListener("click", close);
      document.body.appendChild(scrim); document.body.appendChild(sheet);
      journeyUI._openDialog = { close };
      showTab("driver");
      refreshMeters();
      return { close };
    },

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
      titleEl.textContent = "Anybody hitching with you";
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

      // "Add anonymous" — a co-hitcher with no account. Multiple are allowed; the
      // backend counts "Anonymous" entries in co_hitchhiker into anonymous occupants.
      const anonBtn = document.createElement("button");
      anonBtn.type = "button";
      anonBtn.className = "inr-cohitch-anon";
      anonBtn.innerHTML = '<i class="fa-solid fa-user-secret" aria-hidden="true"></i> Add anonymous';
      anonBtn.addEventListener("click", function () { addAnonymous(); });
      sheet.appendChild(anonBtn);

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

      function addAnonymous() {
        // No account, so no username to dedupe/self-exclude — and multiple anonymous
        // co-hitchers are allowed (the backend counts each "Anonymous" entry).
        selected.push("Anonymous");
        renderChips();
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

    // Slim give-up sheet: rating (required) + optional comment only — no vehicle/signal
    // chips (no ride happened). Replaces the old /ride redirect so a give-up can be captured
    // and queued offline. onSave({ rating, comment }) fires when the user taps Save.
    giveUpSheet(onSave) {
      if (journeyUI._openDialog) journeyUI._openDialog.close();

      const scrim = document.createElement("div");
      scrim.className = "inride-scrim";

      const sheet = document.createElement("div");
      sheet.className = "inr-sheet";

      const grab = document.createElement("div");
      grab.className = "inr-sheet__grab";
      sheet.appendChild(grab);

      // Explicit close so the user isn't forced to log a give-up just because the sheet
      // opened — dismisses without onSave, leaving the journey in its current (waiting) state.
      const closeX = document.createElement("button");
      closeX.type = "button";
      closeX.className = "inr-sheet__close";
      closeX.setAttribute("aria-label", "Close");
      closeX.innerHTML = "&times;";
      closeX.addEventListener("click", function () { close(); });
      sheet.appendChild(closeX);

      const titleEl = document.createElement("h4");
      titleEl.textContent = "How was the spot?";
      sheet.appendChild(titleEl);

      const subEl = document.createElement("p");
      subEl.className = "inr-sheet__sub";
      subEl.textContent = "You waited here without a ride — rate the spot so others know.";
      sheet.appendChild(subEl);

      // ── 5-star rating (required — Save stays disabled until a star is tapped) ──
      let rating = 0;
      const starsEl = document.createElement("div");
      starsEl.className = "inr-stars";
      const starEls = [];
      for (let i = 1; i <= 5; i++) {
        const star = document.createElement("span");
        star.className = "inr-star";
        star.setAttribute("data-value", String(i));
        star.textContent = "★";
        star.addEventListener("click", (function (val) {
          return function () { rating = val; updateStars(); updateSaveBtn(); };
        }(i)));
        starsEl.appendChild(star);
        starEls.push(star);
      }
      function updateStars() {
        starEls.forEach(function (s, idx) { s.classList.toggle("inr-star--on", idx < rating); });
      }
      sheet.appendChild(starsEl);

      // ── Optional comment ──────────────────────────────────────────────────────
      const commentField = document.createElement("div");
      commentField.className = "inr-field";
      const commentLabel = document.createElement("label");
      commentLabel.textContent = "Comment (optional)";
      commentField.appendChild(commentLabel);
      const textarea = document.createElement("textarea");
      textarea.className = "inr-sheet__textarea";
      textarea.placeholder = "e.g. no traffic, bad pull-in spot…";
      commentField.appendChild(textarea);
      sheet.appendChild(commentField);

      // ── Save CTA (disabled until a rating is chosen) ──────────────────────────
      const saveBtn = document.createElement("button");
      saveBtn.type = "button";
      saveBtn.className = "inr-big inr-big--green inr-sheet__save inr-disabled";
      saveBtn.disabled = true;
      saveBtn.innerHTML = '<i class="fa-solid fa-check"></i> Save';
      function updateSaveBtn() {
        saveBtn.disabled = rating === 0;
        saveBtn.classList.toggle("inr-disabled", rating === 0);
      }
      saveBtn.addEventListener("click", function () {
        if (!rating) return;
        close();
        onSave({ rating: rating, comment: textarea.value.trim() });
      });
      sheet.appendChild(saveBtn);

      function close() {
        if (scrim.parentNode) scrim.parentNode.removeChild(scrim);
        if (sheet.parentNode) sheet.parentNode.removeChild(sheet);
        journeyUI._openDialog = null;
      }
      scrim.addEventListener("click", close);

      document.body.appendChild(scrim);
      document.body.appendChild(sheet);
      journeyUI._openDialog = { close };
      return { close };
    },

    // Optional nudge on Finish: if driver/vehicle details are incomplete, offer to add
    // them before saving. "Add details" opens the details sheet then continues; "Skip"
    // continues straight to the forced would-ride-again gate. Never blocks — details are
    // optional. seed is the current j.details; onAdd(fields) fires after a save, onSkip()
    // when the user declines. Callers skip this entirely at 100% (nothing to nudge).
    finishNudge(pct, seed, onAdd, onSkip) {
      // `forced` (no scrim dismissal) so the only exits are the two explicit buttons —
      // both proceed the finish, exactly once. Routing a scrim-dismiss through dialog's
      // onClose would double-fire on the "Add details" tap (close() runs before onClick).
      journeyUI.dialog({
        title: "Add driver & vehicle details?",
        body: "This ride is " + pct + "% complete. Help your fellow hitchers?",
        centered: true,
        forced: true,
        actions: [
          // "Add details" opens the details sheet (which closes this dialog via the
          // single-flight guard); its Save fires onAdd, which then continues the finish.
          { label: "Add details", cls: "inr-go", onClick: function () {
            journeyUI.detailsSheet(seed, function (fields) { onAdd(fields); });
          } },
          { label: "Skip", cls: "inr-grey", onClick: function () { onSkip(); } },
        ],
      });
    },

    // Forced would-ride-again gate on finish: a required Yes/No with no dismissal.
    // Deliberately NOT part of the completeness score — a per-ride sentiment we always
    // capture, independent of the demographic points.
    wouldRideAgainSheet(onAnswer) {
      journeyUI.dialog({
        title: "Would you accept this ride again?",
        body: "One quick question before we save this ride.",
        centered: true,
        forced: true,
        actions: [
          { label: "Yes", cls: "inr-go",   onClick: function () { onAnswer(true); } },
          { label: "No",  cls: "inr-grey", onClick: function () { onAnswer(false); } },
        ],
      });
    },

    dialog({ title, body, actions, onClose, centered, forced }) {
      // Close any already-open dialog so rapid re-triggers don't stack overlays.
      if (journeyUI._openDialog) journeyUI._openDialog.close();

      // Scrim covers the whole viewport; tapping it cancels the dialog.
      const scrim = document.createElement("div");
      scrim.className = "inride-scrim";

      const card = document.createElement("div");
      // centered: screen-centre modal (e.g. the "Track your rides?" prompt) instead of the
      // default bottom card used for thumb-reachable spot actions.
      card.className = "inride-dialog" + (centered ? " inride-dialog--centered" : "");

      const h = document.createElement("h4");
      h.textContent = title;
      card.appendChild(h);

      const p = document.createElement("p");
      p.textContent = body;
      card.appendChild(p);

      const actionsEl = document.createElement("div");
      actionsEl.className = "inr-actions";

      function close() {
        if (scrim.parentNode) scrim.parentNode.removeChild(scrim);
        if (card.parentNode) card.parentNode.removeChild(card);
        journeyUI._openDialog = null;
        // Fires on ANY dismissal (button or scrim tap) so callers can clean up
        // transient chrome they attached alongside the dialog (e.g. a preview pin).
        if (onClose) onClose();
      }

      actions.forEach(function (action) {
        const btn = document.createElement("button");
        btn.className = action.cls;
        btn.textContent = action.label;
        btn.addEventListener("click", function () {
          close();
          action.onClick();
        });
        actionsEl.appendChild(btn);
      });

      card.appendChild(actionsEl);

      // Tap the scrim (outside the card) to cancel — unless the dialog is `forced`
      // (a required answer, e.g. would-ride-again on finish), where there is no way out
      // but the action buttons.
      if (!forced) scrim.addEventListener("click", close);

      document.body.appendChild(scrim);
      document.body.appendChild(card);

      journeyUI._openDialog = { close };
      return { close };
    },

    // Confirm-step for choosing a new waiting spot after a drop-off.
    // Reuses the draggable-pin pattern from manualPin with a "Use my location" shortcut.
    //
    // Coordinate contract:
    //   - defaultLatLng IN: {lat, lon}  (drop-off from finish, matches buildFinishBody shape)
    //   - GPS fix (getFixWithRetry): {lat, lon} — moved onto the marker via setLatLng
    //   - onConfirm OUT: marker.getLatLng() → Leaflet LatLng (has .lat / .lng)
    //     nextRide reads latlng.lng, so we must pass a Leaflet LatLng — NOT {lat, lon}.
    //   - onCancel (optional): called when user taps Cancel; used to return to whatsNext.
    setWaitingSpot(defaultLatLng, onConfirm, onCancel) {
      if (!window.L || !window.map) return;

      // Pre-place the pin at the drop-off so one tap confirms (common case: wait here).
      const marker = L.marker([defaultLatLng.lat, defaultLatLng.lon], {
        draggable: true,
        icon: L.icon({
          iconUrl: "/static/markers/marker-icon-2x-green.png",
          shadowUrl: "/static/markers/marker-shadow.png",
          iconSize: [25, 41], iconAnchor: [12, 41],
          popupAnchor: [1, -34], shadowSize: [41, 41],
        }),
      }).addTo(window.map);

      // Tapping the map also repositions the waiting pin (mirrors manualPin / main map UX).
      function onMapClick(e) { marker.setLatLng(e.latlng); }
      window.map.on("click", onMapClick);

      const ui = document.createElement("div");
      ui.className = "location-selection-ui";
      ui.innerHTML = [
        "<h4>Where are you waiting?</h4>",
        "<p>Drag the pin or tap the map, then confirm.</p>",
        '<div class="lsel-actions">',
        // "Use my location" is a positive/neutral action — give it confirm styling so
        // it doesn't read as a dismiss button; Cancel gets lsel-cancel (muted style).
        '<button class="lsel-confirm" id="inr-waiting-myloc">Use my location</button>',
        '<button class="lsel-confirm" id="inr-waiting-confirm">Confirm</button>',
        '<button class="lsel-cancel" id="inr-waiting-cancel">Cancel</button>',
        "</div>",
      ].join("");
      document.body.appendChild(ui);
      // Neutralize overlay markers (e.g. Hitchwiki event pins) while choosing the
      // new waiting spot, so a tap on one repositions the pin instead of opening
      // its sheet. See body.inr-picking rule in style.css.
      document.body.classList.add("inr-picking");

      function cleanup() {
        window.map.removeLayer(marker);
        window.map.off("click", onMapClick);
        document.body.classList.remove("inr-picking");
        if (ui.parentNode) ui.parentNode.removeChild(ui);
      }

      document.getElementById("inr-waiting-myloc").addEventListener("click", function () {
        // GPS fix returns {lat, lon}; convert to array for Leaflet's setLatLng.
        getFixWithRetry().then(
          function (fix) {
            marker.setLatLng([fix.lat, fix.lon]);
            window.map.setView([fix.lat, fix.lon]);
          },
          function () {
            journeyUI.error("Couldn't get your location — drag the pin instead.");
          }
        );
      });

      document.getElementById("inr-waiting-confirm").addEventListener("click", function () {
        // Pass Leaflet LatLng (has .lat / .lng) so nextRide's latlng.lng read is correct.
        const ll = marker.getLatLng();
        cleanup();
        onConfirm(ll);
      });

      // Cancel returns the user to the "What's next?" dialog (e.g. to choose End Hitch).
      document.getElementById("inr-waiting-cancel").addEventListener("click", function () {
        cleanup();
        if (onCancel) onCancel();
      });
    },
  };

  // ── Entry point from map gestures ────────────────────────────────────────────
  // Returns true if we handled the gesture (so map.js skips its old behavior).
  // Returning false is defensive — currently we always handle when no journey
  // is active, but the fallback keeps the contract explicit.
  window.inrideOnEntryGesture = function (latlng, containerPoint) {
    // One journey at a time. While a journey is active we swallow map gestures so the user
    // can NEVER accidentally drop a pin — EXCEPT once the Finish pin picker is open, where a
    // long-press deliberately repositions the destination pin (the finish location). The
    // picker itself is opened only by the explicit "Finish Ride" button, so long-press can
    // drop a pin only inside that flow. Swallowing otherwise also stops a stray gesture from
    // stacking a second picker card (duplicate ids would break Confirm/Cancel).
    if (journeyStore.get()) {
      if (journeyUI._picking && journeyUI._setPin) journeyUI._setPin(latlng);
      return true;
    }

    // Drop a preview pin at the pressed location so the user can SEE where the
    // journey / spot will start while the choose-action dialog is up (the dialog's
    // scrim dims but doesn't hide it). Removed on any dismissal via onClose. It is
    // static — the semi-transparent scrim blocks dragging anyway; Start Hitching /
    // Log a past ride use the original latlng/containerPoint.
    let previewPin = null;
    if (window.L && window.map) {
      previewPin = L.marker(latlng, {
        icon: L.icon({
          iconUrl: "/static/markers/marker-icon-2x-red.png",
          shadowUrl: "/static/markers/marker-shadow.png",
          iconSize: [25, 41], iconAnchor: [12, 41], shadowSize: [41, 41],
        }),
      }).addTo(window.map);
    }

    journeyUI.dialog({
      title: "This spot",
      body: "Track a ride from here now — or log a ride you already got.",
      onClose: () => { if (previewPin && window.map) window.map.removeLayer(previewPin); previewPin = null; },
      actions: [
        {
          label: "Start Hitching",
          cls: "inr-go",
          onClick: () => journeyFlow.startFromChoose(latlng),
        },
        {
          label: "Log a past ride",
          cls: "inr-ghost",
          // Reuses the existing add-spot flow unchanged; only the label differs.
          onClick: () => window.startAddSpotFromGesture(latlng, containerPoint),
        },
        {
          label: "Propose a spot",
          cls: "inr-ghost",
          // Flags a promising spot (blue marker) without logging a ride — never
          // published to Nostr, just stored server-side with a short comment.
          onClick: () => window.startProposeSpotFromGesture(latlng, containerPoint),
        },
      ],
    });
    return true;
  };

  // ── outboxUI: pending-upload chip + detail sheet ─────────────────────────────
  // The chip shows whenever the outbox is non-empty; it turns into a warning when any
  // item permanently failed. Tapping it opens a sheet to see status and Retry / Discard.
  const outboxUI = {
    _chip: null,

    // Relative age like "2m" / "1h" for a queued item.
    _age(ms) {
      const s = Math.floor((Date.now() - ms) / 1000);
      if (s < 60) return s + "s";
      if (s < 3600) return Math.floor(s / 60) + "m";
      return Math.floor(s / 3600) + "h";
    },

    // Create/update/remove the chip to match the current outbox contents.
    refresh() {
      const all = outboxStore.get();
      if (!all.length) {
        if (outboxUI._chip && outboxUI._chip.parentNode) outboxUI._chip.parentNode.removeChild(outboxUI._chip);
        outboxUI._chip = null;
        return;
      }
      const failed = all.some((it) => it.status === "failed");
      if (!outboxUI._chip) {
        const chip = document.createElement("button");
        chip.id = "inr-outbox-chip";
        chip.type = "button";
        chip.addEventListener("click", outboxUI.openSheet);
        document.body.appendChild(chip);
        outboxUI._chip = chip;
      }
      outboxUI._chip.classList.toggle("inr-outbox-chip--failed", failed);
      outboxUI._chip.innerHTML = failed
        ? '<i class="fa-solid fa-triangle-exclamation"></i> ' + all.length + " to upload"
        : '<i class="fa-solid fa-rotate"></i> ' + all.length + " to upload";
    },

    // Bottom sheet listing each queued item with per-item status and actions.
    openSheet() {
      if (journeyUI._openDialog) journeyUI._openDialog.close();

      const scrim = document.createElement("div");
      scrim.className = "inride-scrim";
      const sheet = document.createElement("div");
      sheet.className = "inr-sheet";

      function close() {
        if (scrim.parentNode) scrim.parentNode.removeChild(scrim);
        if (sheet.parentNode) sheet.parentNode.removeChild(sheet);
        journeyUI._openDialog = null;
      }

      function rebuild() {
        sheet.innerHTML = "";
        const grab = document.createElement("div");
        grab.className = "inr-sheet__grab";
        sheet.appendChild(grab);

        const items = outboxStore.get();
        if (!items.length) { close(); return; } // nothing left — dismiss

        const titleEl = document.createElement("h4");
        titleEl.textContent = "Rides to upload";
        sheet.appendChild(titleEl);

        const list = document.createElement("div");
        list.className = "inr-outbox-list";
        items.forEach((it) => {
          const row = document.createElement("div");
          row.className = "inr-outbox-row";

          const info = document.createElement("div");
          info.className = "inr-outbox-row__info";
          // Build with DOM nodes + textContent, never innerHTML: it.lastError is a
          // server-provided string (persisted in localStorage) and would be an XSS
          // vector if interpolated into markup.
          const kindLabel = it.kind === "giveup" ? "Gave up" : "Ride";
          const strong = document.createElement("strong");
          strong.textContent = kindLabel;
          info.appendChild(strong);
          info.appendChild(document.createTextNode(" · " + outboxUI._age(it.createdAt) + " ago"));
          info.appendChild(document.createElement("br"));
          const statusEl = document.createElement("span");
          if (it.status === "failed") {
            statusEl.className = "inr-outbox-row__err";
            statusEl.textContent = "Couldn't save: " + (it.lastError || "rejected");
          } else {
            statusEl.className = "inr-outbox-row__wait";
            statusEl.textContent = "Waiting for connection…";
          }
          info.appendChild(statusEl);
          row.appendChild(info);

          const actions = document.createElement("div");
          actions.className = "inr-outbox-row__actions";

          // Details → view/edit the queued ride (rating, comment, timestamps) before upload.
          const details = document.createElement("button");
          details.type = "button";
          details.className = "inr-outbox-row__btn";
          details.title = "Details / edit";
          details.innerHTML = '<i class="fa-solid fa-pen"></i>';
          details.addEventListener("click", function () {
            close();               // swap the list for the edit sheet (single dialog at a time)
            outboxUI.editSheet(it); // returns to the list on dismissal
          });
          actions.appendChild(details);

          // Delete → any queued ride (pending or failed), guarded by a confirm.
          const del = document.createElement("button");
          del.type = "button";
          del.className = "inr-outbox-row__btn inr-outbox-row__btn--danger";
          del.title = "Delete";
          del.innerHTML = '<i class="fa-solid fa-trash"></i>';
          del.addEventListener("click", function () {
            if (window.confirm("Delete this ride? It won't be uploaded.")) {
              outboxStore.remove(it.id);
              outboxUI.refresh();
              rebuild();
            }
          });
          actions.appendChild(del);

          row.appendChild(actions);
          list.appendChild(row);
        });
        sheet.appendChild(list);

        // Retry all: reset failed items to pending and kick a flush.
        if (items.some((it) => it.status === "failed")) {
          const retry = document.createElement("button");
          retry.type = "button";
          retry.className = "inr-big inr-big--green inr-sheet__save";
          retry.innerHTML = '<i class="fa-solid fa-rotate"></i> Retry now';
          retry.addEventListener("click", function () {
            outboxStore.get().forEach(function (it) {
              if (it.status === "failed") outboxStore.update(it.id, { status: "pending" });
            });
            outboxUI.refresh();
            flushOutbox().then(function () { outboxUI.refresh(); rebuild(); });
            rebuild();
          });
          sheet.appendChild(retry);
        }

        const closeBtn = document.createElement("button");
        closeBtn.type = "button";
        closeBtn.className = "inr-sheet__more";
        closeBtn.textContent = "Close";
        closeBtn.addEventListener("click", close);
        sheet.appendChild(closeBtn);
      }

      scrim.addEventListener("click", close);
      rebuild();
      document.body.appendChild(scrim);
      document.body.appendChild(sheet);
      journeyUI._openDialog = { close };
    },

    // View/edit a queued ride before it uploads. Editable: rating, wait, comment, and the
    // pickup/arrival timestamps (finish rides only — a give-up has no timestamps). Edits are
    // made on a COPY and only committed to the outbox on Save, which also resets a failed
    // item to pending so the corrected ride retries. Dismissing returns to the list sheet.
    editSheet(item) {
      if (journeyUI._openDialog) journeyUI._openDialog.close();
      const body = Object.assign({}, item.body); // work on a copy; commit on Save

      const scrim = document.createElement("div");
      scrim.className = "inride-scrim";
      const sheet = document.createElement("div");
      sheet.className = "inr-sheet";

      const grab = document.createElement("div");
      grab.className = "inr-sheet__grab";
      sheet.appendChild(grab);

      const titleEl = document.createElement("h4");
      titleEl.textContent = item.kind === "giveup" ? "Gave-up spot" : "Ride details";
      sheet.appendChild(titleEl);

      // ── Rating (required) ──
      let rating = Number(body.rate) || 0;
      const starsEl = document.createElement("div");
      starsEl.className = "inr-stars";
      const starEls = [];
      for (let i = 1; i <= 5; i++) {
        const star = document.createElement("span");
        star.className = "inr-star" + (i <= rating ? " inr-star--on" : "");
        star.textContent = "★";
        star.addEventListener("click", (function (val) {
          return function () {
            rating = val;
            starEls.forEach(function (s, idx) { s.classList.toggle("inr-star--on", idx < rating); });
          };
        }(i)));
        starsEl.appendChild(star);
        starEls.push(star);
      }
      sheet.appendChild(starsEl);

      // Small helper: labeled field wrapper.
      function field(labelText, input) {
        const f = document.createElement("div");
        f.className = "inr-field";
        const l = document.createElement("label");
        l.textContent = labelText;
        f.appendChild(l);
        f.appendChild(input);
        sheet.appendChild(f);
      }

      // ── Timestamps: finish rides carry datetime_ride (pickup) + arrival_datetime; a
      //    give-up has neither, so only render the inputs that exist in the body. Values
      //    are already "YYYY-MM-DDTHH:mm" (isoLocal), which is exactly datetime-local's format.
      let departureInput = null, arrivalInput = null;
      if (body.datetime_ride) {
        departureInput = document.createElement("input");
        departureInput.type = "datetime-local";
        departureInput.className = "inr-input";
        departureInput.value = body.datetime_ride;
        field("Picked up", departureInput);
      }
      if (body.arrival_datetime) {
        arrivalInput = document.createElement("input");
        arrivalInput.type = "datetime-local";
        arrivalInput.className = "inr-input";
        arrivalInput.value = body.arrival_datetime;
        field("Arrived", arrivalInput);
      }

      // ── Wait (minutes) ──
      const waitInput = document.createElement("input");
      waitInput.type = "number";
      waitInput.min = "0";
      waitInput.className = "inr-input";
      waitInput.value = body.wait || "0";
      field("Wait (minutes)", waitInput);

      // ── Comment ──
      const textarea = document.createElement("textarea");
      textarea.className = "inr-sheet__textarea";
      textarea.value = body.comment || "";
      field("Comment (optional)", textarea);

      // Read-only coordinates for reference.
      const coords = document.createElement("p");
      coords.className = "inr-sheet__sub";
      const hasDest = body.destination_lat !== "" && body.destination_lat != null;
      coords.textContent = "From " + Number(body.pickup_lat).toFixed(4) + ", " + Number(body.pickup_lon).toFixed(4) +
        (hasDest ? "  →  " + Number(body.destination_lat).toFixed(4) + ", " + Number(body.destination_lon).toFixed(4) : "");
      sheet.appendChild(coords);

      const errEl = document.createElement("p");
      errEl.className = "inr-outbox-row__err";
      errEl.style.display = "none";
      sheet.appendChild(errEl);

      // Dismissing (save, cancel, or scrim) returns to the list sheet.
      function close() {
        if (scrim.parentNode) scrim.parentNode.removeChild(scrim);
        if (sheet.parentNode) sheet.parentNode.removeChild(sheet);
        journeyUI._openDialog = null;
        outboxUI.openSheet();
      }

      const saveBtn = document.createElement("button");
      saveBtn.type = "button";
      saveBtn.className = "inr-big inr-big--green inr-sheet__save";
      saveBtn.innerHTML = '<i class="fa-solid fa-check"></i> Save changes';
      saveBtn.addEventListener("click", function () {
        if (!rating) { errEl.textContent = "Please choose a rating."; errEl.style.display = ""; return; }
        // Backend asserts arrival > departure when both present — validate here so an edit
        // can't push the item into a permanent 400.
        if (departureInput && arrivalInput && departureInput.value && arrivalInput.value &&
            arrivalInput.value <= departureInput.value) {
          errEl.textContent = "Arrival must be after the pickup time."; errEl.style.display = ""; return;
        }
        body.rate = String(rating);
        body.wait = String(Math.max(0, parseInt(waitInput.value, 10) || 0));
        body.comment = textarea.value.trim();
        if (departureInput) body.datetime_ride = departureInput.value;
        if (arrivalInput) body.arrival_datetime = arrivalInput.value;
        // Committing an edit resets a failed item to pending so the fix gets retried.
        outboxStore.update(item.id, { body: body, status: "pending", lastError: null });
        outboxUI.refresh();
        close();
        flushOutbox();
      });
      sheet.appendChild(saveBtn);

      const cancelBtn = document.createElement("button");
      cancelBtn.type = "button";
      cancelBtn.className = "inr-sheet__more";
      cancelBtn.textContent = "Cancel";
      cancelBtn.addEventListener("click", close);
      sheet.appendChild(cancelBtn);

      scrim.addEventListener("click", close);
      document.body.appendChild(scrim);
      document.body.appendChild(sheet);
      journeyUI._openDialog = { close };
    },
  };

  window.inride = { journeyStore, journeyUI, journeyFlow, outboxStore, submitBody, flushOutbox, outboxUI };

  // ── On-load init ─────────────────────────────────────────────────────────────

  const STALE_MS = 24 * 60 * 60 * 1000; // 24 h: threshold for "Welcome back" affordance

  // Determine the last-active timestamp for staleness detection.
  // waiting  → waitSegmentStartMs (current segment's anchor in localStorage)
  // paused   → approximate journey-start (now minus banked wait; no explicit pause-time stored)
  // in-ride  → gotRideMs (when the user boarded)
  function lastActiveMs(j) {
    if (j.state === "waiting") return j.waitSegmentStartMs || Date.now();
    if (j.state === "in-ride") return j.gotRideMs || Date.now();
    // paused: waitSegmentStartMs is null; derive from banked total as best available proxy
    return Date.now() - (j.waitAccumMs || 0);
  }

  // Rehydrate on load: restore the docked UI + timer for an in-progress journey.
  // Also complete a login round-trip (pendingStart) begun from the soft prompt.
  function initInride() {
    // Complete the login round-trip: the "Log in" button stashed the chosen spot in
    // PENDING_KEY before redirecting; on return we pick it up and start the journey.
    const pend = localStorage.getItem(PENDING_KEY);
    if (pend && window.IS_LOGGED_IN) {
      localStorage.removeItem(PENDING_KEY);
      // return is INSIDE the try so a malformed PENDING_KEY that throws falls through
      // to the store-resume path below instead of short-circuiting the whole init.
      try { const p = JSON.parse(pend); journeyFlow.beginWithCoHitchers(L.latLng(p.lat, p.lon)); return; } catch (e) {}
    } else if (pend) {
      // Returned still anonymous (login cancelled or failed) — discard the stash.
      localStorage.removeItem(PENDING_KEY);
    }

    // Non-blocking load of score weights and driver-info choices so the in-ride sheet
    // can render and score synchronously once the user reaches the demographics step.
    loadDemographicData();

    const j = journeyStore.get();
    if (!j) return;

    // Old-journey affordance: if the current segment's anchor is > 24 h old, offer
    // Resume (restore as-is) or Discard before drawing the timer and dock, so the
    // user isn't silently dropped into a stale journey after overnight or longer.
    if (Date.now() - lastActiveMs(j) > STALE_MS) {
      journeyUI.dialog({
        title: "Welcome back!",
        body: "You have a hitching journey from more than 24 hours ago. Continue where you left off?",
        actions: [
          { label: "Resume",  cls: "inr-go", onClick: function () { journeyUI.render(j); } },
          { label: "Discard", cls: "inr-grey",    onClick: function () { journeyFlow.end(); } },
        ],
      });
      return;
    }

    journeyUI.render(j); // waiting | paused | in-ride
  }

  // Periodic flush while items are pending. Self-clearing so an empty outbox costs no
  // timer. Idempotent — safe to call repeatedly (won't stack intervals). This REASSIGNS
  // the stub declared near the capture flows (which needed to call it before this point).
  let outboxTimer = null;
  startOutboxTimer = function () {
    if (outboxTimer) return;
    outboxTimer = setInterval(function () {
      if (!outboxStore.pending().length) { clearInterval(outboxTimer); outboxTimer = null; return; }
      flushOutbox();
    }, 30000);
  };

  // Reconnect → drain immediately (don't wait for the interval).
  window.addEventListener("online", function () { flushOutbox(); });

  // On load: restore the chip and, if a previous session left queued rides, flush + tick.
  function initOutbox() {
    outboxUI.refresh();
    if (outboxStore.pending().length) { flushOutbox(); startOutboxTimer(); }
  }

  // Run only after Leaflet's window.map is ready — _renderInRide places a Leaflet marker
  // and needs the map instance to exist first. Poll at 100 ms; interval clears itself.
  if (window.map) { initInride(); initOutbox(); }
  else { const t = setInterval(function () { if (window.map) { clearInterval(t); initInride(); initOutbox(); } }, 100); }
})();
