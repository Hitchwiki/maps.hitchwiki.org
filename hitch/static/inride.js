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
    // journeyUI.render is a stub until Task 5; call defensively in case order varies.
    journeyUI.render && journeyUI.render(j);
  };

  // ── journeyUI ────────────────────────────────────────────────────────────────
  // Renders a scrim + bottom card mirroring .location-selection-ui.
  // Returns a close handle { close() } so callers can dismiss programmatically.
  const journeyUI = {
    _openDialog: null, // guard: only one dialog open at a time (see Task-3 note)

    // Stub until Task 5 fills in the waiting-state UI.
    render(j) {
      console.log("[inride] render state:", j && j.state, j);
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
