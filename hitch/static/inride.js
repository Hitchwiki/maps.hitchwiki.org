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

  // ── journeyFlow ──────────────────────────────────────────────────────────────
  const journeyFlow = {};

  // Soft login gate: logged-in users go straight to start; anonymous users see a
  // prompt so they can choose to log in (and preserve the chosen spot across the
  // redirect) or carry on without an account. No hard block — anonymous is fine.
  journeyFlow.startFromChoose = function (latlng) {
    if (window.IS_LOGGED_IN) return journeyFlow.start(latlng);
    journeyUI.dialog({
      title: "Track your rides?",
      body: "Log in to keep your ride history, or just continue anonymously.",
      actions: [
        {
          label: "Log in",
          cls: "inr-primary",
          onClick: () => {
            // Stash the chosen pickup so we can resume after the redirect back.
            localStorage.setItem(PENDING_KEY, JSON.stringify({ lat: latlng.lat, lon: latlng.lng }));
            window.location.href = "/login?next=/";
          },
        },
        { label: "Continue anonymously", cls: "inr-grey", onClick: () => journeyFlow.start(latlng) },
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
  journeyFlow.start = function (latlng) {
    const j = journeyStore.set({
      state: "waiting",
      pickup: { lat: latlng.lat, lon: latlng.lng },
      waitAccumMs: 0,
      waitSegmentStartMs: Date.now(),
      gotRideMs: null,
      finalWaitMs: null,
      details: null,
      legIndex: 0,
    });
    journeyUI.render(j);
  };

  // ── journeyUI ────────────────────────────────────────────────────────────────
  // Renders a scrim + bottom card mirroring .location-selection-ui.
  // Returns a close handle { close() } so callers can dismiss programmatically.
  const journeyUI = {
    _openDialog: null,   // guard: only one dialog open at a time (see Task-3 note)
    _tickInterval: null, // 1-s live-timer interval; at most one running at a time
    _dockEl: null,       // the persistent docked action bar
    _chipEl: null,       // the status chip above the dock

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
    },

    // Single entry point for all journey-state rendering.
    // Always tears down first so re-renders (state changes, reloads) start clean.
    render(j) {
      journeyUI.teardown();
      if (!j) return;

      switch (j.state) {
        case "waiting":
          journeyUI._renderWaiting(j);
          break;
        case "paused":
          journeyUI._renderPaused(j);
          break;
        case "in-ride":
          // TODO(Task 9): render the in-ride state (single orange Finish Ride button).
          console.log("[inride] in-ride render not yet implemented (Task 9)");
          break;
        default:
          console.log("[inride] render: unknown state", j.state);
      }
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

      // ── Docked action bar ──────────────────────────────────────────────────
      const dock = document.createElement("div");
      dock.className = "inr-dock";

      // Give Up (red) — implemented in Task 7; wired defensively.
      const giveUpBtn = document.createElement("button");
      giveUpBtn.className = "inr-big inr-big--red";
      giveUpBtn.innerHTML = '<i class="fa-solid fa-flag"></i> Give Up';
      giveUpBtn.addEventListener("click", function () {
        // journeyFlow.giveUp is implemented in Task 7; tapping is a no-op until it lands.
        journeyFlow.giveUp && journeyFlow.giveUp();
      });
      dock.appendChild(giveUpBtn);

      // Got a Ride! (green) — implemented in Task 8; wired defensively.
      const gotRideBtn = document.createElement("button");
      gotRideBtn.className = "inr-big inr-big--green";
      gotRideBtn.innerHTML = '<i class="fa-solid fa-thumbs-up"></i> Got a Ride!';
      gotRideBtn.addEventListener("click", function () {
        // journeyFlow.gotRide is implemented in Task 8; tapping is a no-op until it lands.
        journeyFlow.gotRide && journeyFlow.gotRide();
      });
      dock.appendChild(gotRideBtn);

      document.body.appendChild(dock);
      journeyUI._dockEl = dock;
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

      // ── Docked action bar ────────────────────────────────────────────────────
      const dock = document.createElement("div");
      dock.className = "inr-dock";

      // Give Up (red) — active even while paused; implemented in Task 7.
      const giveUpBtn = document.createElement("button");
      giveUpBtn.className = "inr-big inr-big--red";
      giveUpBtn.innerHTML = '<i class="fa-solid fa-flag"></i> Give Up';
      giveUpBtn.addEventListener("click", function () {
        journeyFlow.giveUp && journeyFlow.giveUp();
      });
      dock.appendChild(giveUpBtn);

      // Got a Ride! — disabled while paused so accidental taps can't cut the wait short.
      const gotRideBtn = document.createElement("button");
      gotRideBtn.className = "inr-big inr-big--green inr-disabled";
      gotRideBtn.disabled = true;
      gotRideBtn.innerHTML = '<i class="fa-solid fa-thumbs-up"></i> Got a Ride!';
      dock.appendChild(gotRideBtn);

      document.body.appendChild(dock);
      journeyUI._dockEl = dock;
    },

    dialog({ title, body, actions }) {
      // Close any already-open dialog so rapid re-triggers don't stack overlays.
      if (journeyUI._openDialog) journeyUI._openDialog.close();

      // Scrim covers the whole viewport; tapping it cancels the dialog.
      const scrim = document.createElement("div");
      scrim.className = "inride-scrim";

      const card = document.createElement("div");
      card.className = "inride-dialog";

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

      // Tap the scrim (outside the card) to cancel.
      scrim.addEventListener("click", close);

      document.body.appendChild(scrim);
      document.body.appendChild(card);

      journeyUI._openDialog = { close };
      return { close };
    },
  };

  // ── Entry point from map gestures ────────────────────────────────────────────
  // Returns true if we handled the gesture (so map.js skips its old behavior).
  // Returning false is defensive — currently we always handle when no journey
  // is active, but the fallback keeps the contract explicit.
  window.inrideOnEntryGesture = function (latlng, containerPoint) {
    // One journey at a time: if one is already running, ignore new gestures.
    if (journeyStore.get()) return true;

    journeyUI.dialog({
      title: "This spot",
      body: "Track a ride from here now — or log a ride you already got.",
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
      ],
    });
    return true;
  };

  window.inride = { journeyStore, journeyUI, journeyFlow }; // more attached in later tasks
})();
