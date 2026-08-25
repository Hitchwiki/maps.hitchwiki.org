// In-ride hitching tracker. A localStorage-backed state machine layered on the
// map. State + timestamps survive reloads so timing keeps running across a long
// wait or an app restart. See docs/superpowers/specs/2026-07-02-in-ride-hitching-tracker-design.md
(function () {
  "use strict";

  // Analytics helper from base.html, resolved once through a local alias so this
  // file stays usable in a bare context where it is absent (same reasoning as
  // routing.js). Never let a missing tracker break the journey.
  const hmTrack = (typeof window !== "undefined" && window.hmTrack) || function () {};

  // map.js's tr() (client-side i18n, see hitch/static/map.js), guarded the same way:
  // this file is eval'd standalone by tests/inride_journey_end.test.js, in a sandbox
  // that never defines tr, so a bare call would throw ReferenceError. Falls back to
  // plain English with {placeholder}s substituted by hand.
  function T(text, vars) {
    if (typeof tr === "function") return tr(text, vars);
    if (!vars) return text;
    return Object.keys(vars).reduce((s, k) => s.split("{" + k + "}").join(vars[k]), text);
  }

  // Minutes a journey has been waiting, for analytics only. Rounded: the exact
  // second is noise, and a coarse number keeps event-data cardinality sane.
  function waitMinutes(j) {
    try {
      return Math.round(journeyStore.currentWaitMs(j, Date.now()) / 60000);
    } catch (e) {
      return 0;
    }
  }

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

  // Every ride this journey has logged so far, oldest first — one entry per Finish and
  // per Give Up. Kept because the whole journey, not the single leg, is what gets closed
  // out at the end: the success overlay needs the LAST ride's facts, and the auto-trip
  // needs all of them. Entry shape:
  //   { id (outbox item id), dTag (server d tag once uploaded), ride (share-card facts), at }
  // Reset by journeyFlow.start (a new journey) and by finalizeJourney (this one is done).
  //
  // Durable, and the d tag is written back into it, because a journey easily outlives the
  // page: a locked phone reloads the PWA between legs, which would otherwise lose the d
  // tags of the legs already uploaded and quietly drop them from the trip.
  const JOURNEY_LOG_KEY = "inride.journeyLog";
  const journeyLogStore = {
    get() {
      try { const v = JSON.parse(localStorage.getItem(JOURNEY_LOG_KEY)); return Array.isArray(v) ? v : []; }
      catch (e) { return []; }
    },
    set(list) { localStorage.setItem(JOURNEY_LOG_KEY, JSON.stringify(list)); return list; },
    add(entry) {
      const l = journeyLogStore.get();
      l.push(entry);
      journeyLogStore.set(l);
      return entry;
    },
    // Fill in the server-assigned d tag for one of the journey's rides once it uploads.
    noteDTag(itemId, dTag) {
      const l = journeyLogStore.get();
      const entry = l.find((e) => e.id === itemId);
      if (!entry || entry.dTag) return;
      entry.dTag = dTag;
      journeyLogStore.set(l);
    },
    clear() { localStorage.removeItem(JOURNEY_LOG_KEY); },
  };

  // A finished multi-ride journey waiting to be grouped into a trip server-side. Durable
  // because the rides may still be sitting in the outbox — a journey hitched through a
  // dead zone must still group itself once the phone reconnects, possibly days later.
  // Shape: { entries: [{ id, dTag|null }], createdAt }.
  const PENDING_TRIP_KEY = "inride.pendingTrip";
  const pendingTripStore = {
    get() {
      try {
        const v = JSON.parse(localStorage.getItem(PENDING_TRIP_KEY));
        return v && Array.isArray(v.entries) ? v : null;
      } catch (e) { return null; }
    },
    set(rec) { localStorage.setItem(PENDING_TRIP_KEY, JSON.stringify(rec)); return rec; },
    clear() { localStorage.removeItem(PENDING_TRIP_KEY); },
    // Fill in the server-assigned d tag for one of the rides once it has uploaded.
    noteDTag(itemId, dTag) {
      const rec = pendingTripStore.get();
      if (!rec) return;
      const entry = rec.entries.find((e) => e.id === itemId);
      if (!entry || entry.dTag) return;
      entry.dTag = dTag;
      pendingTripStore.set(rec);
    },
  };

  // Server-assigned Nostr d tags for rides uploaded in THIS page session, keyed by outbox
  // item id. The client uuid only pins the d tag's suffix (the server prefixes its source),
  // so the real value is knowable no earlier than the upload response — which is what the
  // share card's /ride/<d_tag> link and the auto-trip both need.
  const uploadedDTags = {};

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
  // Normalises Leaflet LatLng (.lng) and plain {lat, lon} to one shape. Every pin picker
  // output passes through this, so .lng never reaches a journey field or a POST body.
  const toLatLon = window.RideSubmit.toLatLon;

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
            // The ride actually reached the server. Finishing a journey only
            // queues it, so without this the funnel would report rides we never
            // received — a hitchhiker on a dead link looks identical to a success.
            hmTrack("journey_ride_uploaded", { kind: item.kind, attempts: item.attempts });
            noteUploaded(item.id, res.json.d_tag);
            outboxStore.remove(item.id);
          } else if (res.status === 400 && res.json && res.json.transient !== true) {
            // Permanently rejected: this ride is lost unless someone intervenes.
            hmTrack("journey_ride_rejected", { kind: item.kind, attempts: item.attempts + 1 });
            outboxStore.update(item.id, {
              status: "failed",
              lastError: (res.json && res.json.error) || T("Rejected"),
              attempts: item.attempts + 1,
            });
          } else {
            outboxStore.update(item.id, {
              lastError: (res.json && res.json.error) || T("Offline"),
              attempts: item.attempts + 1,
            });
          }
        });
      });
    }, Promise.resolve()).then(
      function () {
        flushing = false;
        if (window.inride.outboxUI) window.inride.outboxUI.refresh();
        // A journey waiting to be grouped may have just had its last ride land.
        tryCreateTrip();
      },
      function () { flushing = false; } // never leave the guard stuck on an unexpected throw
    );
  }

  // Record the d tag the server minted for an uploaded ride, everywhere that cares: the
  // in-memory map for this page, and the two durable records that outlive it.
  function noteUploaded(itemId, dTag) {
    if (!dTag) return;
    uploadedDTags[itemId] = dTag;
    journeyLogStore.noteDTag(itemId, dTag);
    pendingTripStore.noteDTag(itemId, dTag);
  }

  // Replaced below (on-load section) with the real interval starter. Declared here so the
  // capture flows can call it before that definition is reached at module-eval time.
  let startOutboxTimer = function () {};

  // Facts the share card draws from, pulled off the /ride body we already built so the
  // two can never disagree. A give-up body carries no destination and no ride times;
  // share_card.js treats those as absent and draws the pickup-only card.
  function rideFactsFromBody(body) {
    return {
      pickupLat: body.pickup_lat,
      pickupLon: body.pickup_lon,
      destLat: body.destination_lat,
      destLon: body.destination_lon,
      waitMin: body.wait,
      departedAt: body.datetime_ride,
      arrivedAt: body.arrival_datetime,
    };
  }

  // ── End of journey: success overlay + auto-grouped trip ──────────────────────
  // How long to wait for a ride's server d tag before the share card settles for linking
  // to the map instead. Nothing is blocked on this — see resolveDTag.
  const DTAG_WAIT_MS = 8000;
  // A pending trip whose rides never uploaded is dropped after this. Far longer than any
  // realistic offline stretch, and it stops a dead record retrying on every page load.
  const PENDING_TRIP_MAX_AGE_MS = 7 * 24 * 3600 * 1000;

  // Resolves with the ride's server-assigned d tag once it uploads, or null when that
  // takes too long or never happens.
  //
  // A promise rather than a value because Give Up finalises the journey in the same
  // breath as queueing the ride: the upload is still in flight, and the d tag decides
  // only whether the share card links to /ride/<d_tag> or to the map. The overlay opens
  // immediately and this wait sits behind the card's own "Drawing your ride…" status,
  // instead of leaving the hitchhiker looking at a bare map for several seconds.
  function resolveDTag(itemId, known) {
    if (known || uploadedDTags[itemId]) return Promise.resolve(known || uploadedDTags[itemId]);
    if (navigator.onLine === false) return Promise.resolve(null);
    return new Promise(function (resolve) {
      const deadline = Date.now() + DTAG_WAIT_MS;
      const poll = setInterval(function () {
        if (uploadedDTags[itemId] || Date.now() > deadline) {
          clearInterval(poll);
          resolve(uploadedDTags[itemId] || null);
        }
      }, 300);
    });
  }

  // Show the map's success overlay — the same one a ride logged through the /ride form
  // gets — for the last ride of the journey. map.js owns the overlay; a context without
  // it (a unit test, an old cached page) simply gets none.
  function showJourneySuccess(entry) {
    if (!entry || typeof window.showPostSubmitOverlay !== "function") return;
    hmTrack("journey_success_shown", {});
    // An anonymous journey routes through the same one-time sign-up nudge an anonymously
    // logged past ride gets; everyone else goes straight to the share card.
    window.showPostSubmitOverlay(window.IS_LOGGED_IN ? "" : "anon", {
      ride: entry.ride,
      dTag: resolveDTag(entry.id, entry.dTag),
    });
  }

  // POST the finished journey's rides to /auto-trip once every one of them has a server
  // d tag. Called after finalising a journey, after each outbox flush, on reconnect and
  // on load, so a journey logged offline groups itself as soon as the phone is back.
  let creatingTrip = false;
  function tryCreateTrip() {
    if (creatingTrip) return;
    const rec = pendingTripStore.get();
    if (!rec) return;
    if (Date.now() - rec.createdAt > PENDING_TRIP_MAX_AGE_MS) return pendingTripStore.clear();
    // Test mode never reaches the real /ride, so there are no real rides to group.
    if (localStorage.getItem("inride.testMode") === "1") return pendingTripStore.clear();

    const queued = new Set(outboxStore.pending().map(function (it) { return it.id; }));
    // A ride still queued may yet upload — wait for it rather than grouping a partial
    // journey we would then never be able to complete (a trip is written once).
    if (rec.entries.some(function (e) { return !e.dTag && queued.has(e.id); })) return;
    // Rides the outbox permanently rejected never got a d tag; the rest still form a trip.
    const dTags = rec.entries.map(function (e) { return e.dTag; }).filter(Boolean);
    if (dTags.length < 2) return pendingTripStore.clear();

    creatingTrip = true;
    fetch("/auto-trip", {
      method: "POST",
      headers: { "X-Requested-With": "inride", "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ ride_d_tags: dTags.join(",") }),
    })
      .then(function (r) {
        return r.json().then(
          function (j) { return { status: r.status, json: j }; },
          function () { return { status: r.status, json: null }; }
        );
      })
      .then(function (res) {
        creatingTrip = false;
        if (res.json && res.json.ok) {
          pendingTripStore.clear();
          hmTrack("journey_trip_created", { rides: dTags.length });
          if (typeof window.showTripCreated === "function") window.showTripCreated(res.json);
        } else if (res.status === 400) {
          // Permanently refused (too few groupable rides, or rides not ours to group).
          // Retrying can only produce the same answer.
          pendingTripStore.clear();
        }
        // Anything else — offline, 5xx — keeps the record for the next attempt.
      })
      .catch(function () { creatingTrip = false; });
  }

  // End of a tracked journey, however it ended: End Hitch, Give Up, cancelling a leg, or
  // discarding a stale one. Kept in one place so every exit closes the journey out the
  // same way rather than only the End Hitch button — what the hitchhiker produced is the
  // journey as a whole, not the leg they happened to stop on.
  function finalizeJourney(opts) {
    const log = journeyLogStore.get();
    journeyStore.clear();
    journeyLogStore.clear();
    journeyUI.teardown();
    if (!log.length) return; // nothing was ever logged — a journey started by mistake
    flushOutbox(); // the last leg was very likely queued moments ago
    // More than one ride means these legs were one hitch, which is information the rides
    // on their own don't carry. Queue the grouping; the POST goes out once they upload.
    if (log.length > 1) {
      pendingTripStore.set({
        entries: log.map(function (e) { return { id: e.id, dTag: e.dTag || uploadedDTags[e.id] || null }; }),
        createdAt: Date.now(),
      });
      tryCreateTrip();
    }
    if (!opts || opts.share !== false) showJourneySuccess(log[log.length - 1]);
  }

  // Enqueue the finished ride durably, THEN proceed — the journey never blocks on the
  // network. The outbox flush (now + on reconnect) performs the actual upload. If the
  // enqueue happens while offline, reassure the user the ride is saved.
  function completeFinish(j, dest, finishMs) {
    // The successful end of the funnel: a ride is now queued for submission.
    // ride_min comes from the boarding timestamp, so it excludes waiting.
    hmTrack("journey_finished", {
      wait_min: Math.round((j.finalWaitMs || 0) / 60000),
      ride_min: j.gotRideMs ? Math.round((finishMs - j.gotRideMs) / 60000) : 0,
      leg: j.legIndex || 0,
    });
    const id = uuid();
    const body = buildFinishBody(j, dest, finishMs, id);
    outboxStore.add({
      id: id, kind: "finish", createdAt: Date.now(), attempts: 0, lastError: null, status: "pending",
      body: body,
    });
    journeyLogStore.add({ id: id, dTag: null, ride: rideFactsFromBody(body), at: Date.now() });
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
  const START_SOURCES = ["start-bar", "spot-sheet", "map-gesture", "route-results"];
  function startSource(source) {
    return START_SOURCES.includes(source) ? source : "unknown";
  }
  journeyFlow.startFromChoose = function (latlng, source) {
    // Callers pass either a Leaflet LatLng (map.js, entry gestures) or {lat, lon}
    // (pinConfirm). Normalise once here so the redirect stash below can't store
    // lon: undefined and silently lose the chosen spot across login.
    const p = toLatLon(latlng);
    source = startSource(source);
    if (window.IS_LOGGED_IN) return journeyFlow.beginWithCoHitchers(p, source);
    hmTrack("journey_track_prompt_shown", { source: source });
    journeyUI.dialog({
      title: T("Track your rides?"),
      body: T("Log in to keep your ride history, or just continue anonymously."),
      centered: true,
      actions: [
        {
          label: T("Log in"),
          cls: "inr-go",
          onClick: () => {
            hmTrack("journey_track_prompt_outcome", { outcome: "login" });
            // Stash the chosen pickup so we can resume after the redirect back.
            localStorage.setItem(
              PENDING_KEY,
              JSON.stringify({ lat: p.lat, lon: p.lon, source: source }),
            );
            window.location.href = "/login?next=/";
          },
        },
        {
          label: T("Continue anonymously"),
          cls: "inr-grey",
          onClick: () => {
            hmTrack("journey_track_prompt_outcome", { outcome: "anonymous" });
            journeyFlow.beginWithCoHitchers(p, source);
          },
        },
      ],
      // A stray scrim tap used to lose the pin the hitchhiker just placed with no
      // way back to it and nothing recorded — the two buttons above are the only
      // paths that started a journey. "No hard block, anonymous is fine" (see the
      // comment above) already says what an unresolved choice should default to;
      // this just makes a dismissal actually take that default instead of losing
      // the journey outright. Distinguished from the explicit buttons in analytics
      // (outcome: "dismissed") so the two are not conflated. Checking `reason ===
      // "scrim"` rather than "not button" on purpose: dialog() calls onClose(undefined)
      // when a *different* dialog force-closes this one (the "one dialog at a time"
      // guard at the top of dialog()), which must not silently start a journey the
      // hitchhiker never chose to start.
      onClose: (reason) => {
        if (reason !== "scrim" && reason !== "cancel-x") return;
        hmTrack("journey_track_prompt_outcome", { outcome: "dismissed" });
        journeyFlow.beginWithCoHitchers(p, source);
      },
    });
  };

  // Bank the running wait segment and freeze the timer — paused time is never
  // counted toward the recorded wait. State transitions: waiting → paused.
  journeyFlow.pause = function () {
    const j = journeyStore.get(); if (!j || j.state !== "waiting") return;
    // Bank the active segment and stop the clock so a break/overnight is excluded.
    j.waitAccumMs = journeyStore.currentWaitMs(j, Date.now());
    // Paused time is excluded from the recorded wait, so a heavily used pause
    // would mean reported waits understate real roadside time.
    hmTrack("journey_paused", { wait_min: waitMinutes(j) });
    j.waitSegmentStartMs = null; j.state = "paused";
    journeyUI.render(journeyStore.set(j));
  };

  // Restart the wait segment from now — continues from where it froze. State: paused → waiting.
  journeyFlow.resume = function () {
    const j = journeyStore.get(); if (!j || j.state !== "paused") return;
    hmTrack("journey_resumed", { wait_min: waitMinutes(j) });
    j.waitSegmentStartMs = Date.now(); j.state = "waiting";
    journeyUI.render(journeyStore.set(j));
  };

  // Seed the waiting journey. Pickup = the chosen latlng; wait timer starts now.
  journeyFlow.start = function (latlng, coHitchhikers, source) {
    // Accepts a Leaflet LatLng or {lat, lon} — see toLatLon.
    const p = toLatLon(latlng);
    // A fresh journey logs nothing yet. nextRide deliberately does NOT do this: its legs
    // belong to the journey already in progress.
    journeyLogStore.clear();
    const j = journeyStore.set({
      state: "waiting",
      pickup: { lat: p.lat, lon: p.lon },
      coHitchhikers: coHitchhikers || [],
      waitAccumMs: 0,
      waitSegmentStartMs: Date.now(),
      gotRideMs: null,
      finalWaitMs: null,
      details: null,
      legIndex: 0,
    });
    // Entry point of the in-ride funnel. This is a second, separate contribution
    // path from the /ride form — a journey that reaches Finish or Give up submits
    // a ride without ever touching add_ride_clicked.
    hmTrack("journey_started", {
      co_hitchhikers: (coHitchhikers || []).length,
      source: startSource(source),
    });
    journeyUI.render(j);
  };

  // Show the co-hitcher modal, then seed the journey with whoever was added.
  journeyFlow.beginWithCoHitchers = function (latlng, source) {
    journeyUI.coHitcherSheet(function (coHitchhikers) {
      journeyFlow.start(latlng, coHitchhikers, source);
    });
  };

  // Ends the journey via the dock's × — offers to salvage a real outcome first instead of
  // only discarding. journey_cancelled turned out to be the single most common way a
  // journey ends (146 of 210 journey_started in a 28d window — more than journey_got_ride
  // (74) and journey_gave_up (12) combined), but the old flow gave "I got picked up before
  // I could tap anything else" and "I tapped Start by mistake" the exact same one button,
  // so a real ride behind a cancel went unrecorded. Discard (no track, no data) is still
  // one tap away via the dialog's own dismiss (× / scrim tap) — same as declining the old
  // window.confirm.
  journeyFlow.cancel = function () {
    const j = journeyStore.get();
    if (!j) return;
    journeyUI.dialog({
      title: T("End this journey?"),
      body: T("How did it go?"),
      centered: true,
      cancelButton: true,
      actions: [
        {
          label: T("Got a ride"),
          cls: "inr-go",
          onClick: function () {
            // gotRide only accepts state "waiting"; resume first if paused so the
            // existing state machine handles the transition unchanged.
            if (j.state === "paused") journeyFlow.resume();
            journeyUI.rideDetailsSheet(function (details) { journeyFlow.gotRide(details); });
          },
        },
        {
          label: T("Wasn't picked up"),
          cls: "inr-ghost",
          onClick: function () { journeyFlow.giveUp(); },
        },
        {
          label: T("No, it was a mistake — don't save"),
          cls: "inr-grey",
          onClick: function () { journeyFlow._discardCancel(j); },
        },
      ],
    });
  };

  // The true discard path (formerly the whole of `cancel`): logs journey_cancelled and
  // ends the journey without submitting a ride. Kept separate so the dialog's third
  // button reads as one clear action rather than an inline closure duplicating the
  // tracking call.
  journeyFlow._discardCancel = function (j) {
    // The silent loss: a started journey that produces no ride at all. Distinct
    // from give-up, which does submit one — so this is the count that says how
    // much real hitchhiking the tracker records but never publishes.
    hmTrack("journey_cancelled", { from_state: j.state, wait_min: waitMinutes(j), leg: j.legIndex || 0 });
    // Only the *current* leg's wait is thrown away. Earlier legs of the same journey are
    // already-logged rides, so this still ends the journey properly — success overlay and
    // auto-trip included — rather than silently dropping what was recorded.
    finalizeJourney({ share: true });
  };

  // Gave up waiting. Capture a rating + comment inline (no redirect — the /ride form
  // won't load offline), then enqueue a destination-less ride (backend stores NaN dest).
  // The wait is pause-aware and frozen at give-up time.
  journeyFlow.giveUp = function () {
    const j = journeyStore.get(); if (!j) return;
    const waitMin = Math.round(journeyStore.currentWaitMs(j, Date.now()) / 60000);
    // Tracked inside the sheet callback, not before it: opening the give-up sheet
    // and then backing out of it is not giving up, and counting it as such would
    // overstate the failure rate.
    journeyUI.giveUpSheet(function (details) {
      hmTrack("journey_gave_up", { wait_min: waitMin, leg: j.legIndex || 0 });
      const id = uuid();
      const body = window.RideSubmit.buildGiveUpBody(j, waitMin, details, id);
      outboxStore.add({
        id: id, kind: "giveup", createdAt: Date.now(), attempts: 0, lastError: null, status: "pending",
        body: body,
      });
      journeyLogStore.add({ id: id, dTag: null, ride: rideFactsFromBody(body), at: Date.now() });
      if (window.inride.outboxUI) window.inride.outboxUI.refresh();
      startOutboxTimer();
      if (navigator.onLine === false) journeyUI.toast("Saved — will upload when you're back online.");
      // Giving up ends the journey, so it gets the same close-out as End Hitch — the
      // wait it recorded is a logged spot experience like any other.
      finalizeJourney({ share: true });
    });
  };

  // Boarded: departure time = now, wait is frozen (pause-aware), ride details are
  // captured; submission is deferred to Finish Ride (destination not known yet).
  journeyFlow.gotRide = function (details) {
    const j = journeyStore.get(); if (!j || (j.state !== "waiting")) return;
    // The wait paid off. wait_min here is the real thing people want to know
    // about a spot, and it is measured rather than remembered after the fact.
    hmTrack("journey_got_ride", { wait_min: waitMinutes(j), leg: j.legIndex || 0 });
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
      // Step 1: confirm the drop-off on the map. ALWAYS asked, on every leg including the
      // last one before End Hitch. A silent GPS fix logged the ride wherever the user
      // happened to be when they pressed Finish — often a café hours after arriving — and
      // nothing downstream could tell that apart from a real drop-off. The picker opens
      // instantly and locates in the background, so Finish never blocks on GPS.
      journeyUI.pinConfirm({
        title: T("Where did you get out?"),
        hint: T("Drag the pin or tap the map, then confirm."),
        confirmLabel: T("Confirm Drop-off"),
        seed: null,
        color: "orange",
        autoLocate: true,
        myLocation: true,
        // Same outcome vocabulary as the start-bar's journey_start_picker (B358's own
        // flagged next step: this picker was the other autoLocate:true pinConfirm call
        // site with no outcome tracking at all, leaving auto-location-failure rate on
        // arrival completely invisible).
        onOutcome: function (outcome, details) {
          hmTrack("journey_finish_picker", Object.assign({ outcome: outcome }, details));
        },
        onConfirm: askAndSubmit,
        // Aborting the picker must not discard the journey: stay in-ride with the button
        // released so Finish can be pressed again.
        onCancel: function () { journeyUI.setFinishBusy(false); },
      });
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
  // `dropoff` is now a point the user confirmed on the map at Finish, not a silent GPS
  // fix — so waiting there needs no second picker. Only actually moving does.
  journeyFlow.whatsNext = function (dropoff) {
    // Clear the in-ride dock, chip, pickup pin, and tick interval so they don't
    // show through behind the dialog. State remains in-ride in the store until
    // nextRide (which calls render) or end (which calls teardown again harmlessly).
    journeyUI.teardown();
    journeyUI.dialog({
      title: T("What's next?"),
      body: T("Ride saved — dropped off here. Waiting for another ride?"),
      actions: [
        { label: T("Next ride from here"), cls: "inr-go", onClick: () => journeyFlow.nextRide(dropoff) },
        {
          label: T("Wait somewhere else"),
          cls: "inr-ghost",
          // Dropped at a motorway exit and walking to a better on-ramp: the walked-to
          // spot is the one worth logging, so this must stay reachable.
          onClick: () => journeyUI.pinConfirm({
            title: T("Where are you waiting?"),
            hint: T("Drag the pin or tap the map, then confirm."),
            confirmLabel: T("Confirm"),
            seed: dropoff,
            color: "green",
            // The confirmed drop-off is a better default here than a fresh fix.
            autoLocate: false,
            myLocation: true,
            // autoLocate is off here (seeded from the just-confirmed drop-off instead), so
            // auto-location-* outcomes never fire -- confirmed/cancelled/location-button-*
            // are the only ones possible. Tracked anyway for the same reason as the other
            // pinConfirm call sites: abandonment here (cancelled) is otherwise invisible.
            onOutcome: function (outcome, details) {
              hmTrack("journey_wait_picker", Object.assign({ outcome: outcome }, details));
            },
            onConfirm: journeyFlow.nextRide,
            // Return to this dialog, or the user is stranded with no way to End Hitch.
            onCancel: () => journeyFlow.whatsNext(dropoff),
          }),
        },
        { label: T("End Hitch"), cls: "inr-grey", onClick: () => journeyFlow.end() },
      ],
    });
  };

  // End the journey: wipe stored state, remove all journey chrome, and close it out with
  // the success overlay for the last ride logged (plus a trip if there were several).
  journeyFlow.end = function () { finalizeJourney({ share: true }); };

  // Same close-out without the overlay, for discarding a journey left over from more than
  // a day ago: whatever it logged still deserves its trip, but a share card for a ride
  // from another day is not a confirmation of anything the user just did.
  journeyFlow.discard = function () { finalizeJourney({ share: false }); };

  // New leg: drop-off is the DEFAULT waiting location but the user can move it
  // (dropped at an exit, walks to a better spot). Fresh timers; pickup = confirmed pt.
  // Accepts a Leaflet LatLng or {lat, lon} — see toLatLon. Called with the confirmed
  // drop-off ("Next ride from here") or a pinConfirm result ("Wait somewhere else").
  journeyFlow.nextRide = function (latlng) {
    const p = toLatLon(latlng);
    const prev = journeyStore.get();
    const j = journeyStore.set({
      state: "waiting", pickup: { lat: p.lat, lon: p.lon },
      waitAccumMs: 0, waitSegmentStartMs: Date.now(),
      gotRideMs: null, finalWaitMs: null, details: null,
      legIndex: (prev && prev.legIndex || 0) + 1,
      coHitchhikers: (prev && prev.coHitchhikers) || [],
    });
    // Continuing a multi-leg trip rather than stopping. journey_started does not
    // fire for these, so the leg counter is the only way to see them.
    hmTrack("journey_next_leg", { leg: j.legIndex });
    journeyUI.render(j);
  };

  // ── journeyUI ────────────────────────────────────────────────────────────────
  // Renders a scrim + bottom card mirroring .location-selection-ui.
  // Returns a close handle { close() } so callers can dismiss programmatically.
  const journeyUI = {
    _openDialog: null,   // guard: only one dialog open at a time (see Task-3 note)
    _picking: false,     // guard: a pin picker (pinConfirm) is open — don't stack another
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
      label.textContent = T("Waiting · {time}", { time: fmtHMS(journeyStore.currentWaitMs(j, Date.now())) });
      chip.appendChild(label);

      // Pause pill: wired defensively — journeyFlow.pause is implemented in Task 6;
      // tapping is a no-op until that task lands.
      const pauseBtn = document.createElement("button");
      pauseBtn.className = "inr-pausepill";
      pauseBtn.innerHTML = '<i class="fa-solid fa-pause"></i> ' + T("Pause");
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
        label.textContent = T("Waiting · {time}", { time: fmtHMS(journeyStore.currentWaitMs(cur, Date.now())) });
      }, 1000);

      // ── Docked action bar (button row + a small grey Cancel beneath) ─────────
      const dock = document.createElement("div");
      dock.className = "inr-dock inr-dock--stack";

      const row = document.createElement("div");
      row.className = "inr-dock-row";

      // Give Up (red) — logs a rated spot experience for the wait.
      const giveUpBtn = document.createElement("button");
      giveUpBtn.className = "inr-big inr-big--red";
      giveUpBtn.innerHTML = '<i class="fa-solid fa-flag"></i> ' + T("Give Up");
      giveUpBtn.addEventListener("click", function () {
        journeyFlow.giveUp && journeyFlow.giveUp();
      });
      row.appendChild(giveUpBtn);

      // Got a Ride! (green) — opens the ride-details sheet; sheet's Ride On! calls gotRide.
      const gotRideBtn = document.createElement("button");
      gotRideBtn.className = "inr-big inr-big--green";
      gotRideBtn.innerHTML = '<i class="fa-solid fa-thumbs-up"></i> ' + T("Got a Ride!");
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
      btn.setAttribute("aria-label", T("Cancel journey"));
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
      label.textContent = T("Paused · waited {time}", { time: fmtHMS(journeyStore.currentWaitMs(j, Date.now())) });
      chip.appendChild(label);

      // Resume pill: restarts the wait segment from now.
      const resumeBtn = document.createElement("button");
      resumeBtn.className = "inr-pausepill";
      resumeBtn.innerHTML = '<i class="fa-solid fa-play"></i> ' + T("Resume");
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
      giveUpBtn.innerHTML = '<i class="fa-solid fa-flag"></i> ' + T("Give Up");
      giveUpBtn.addEventListener("click", function () {
        journeyFlow.giveUp && journeyFlow.giveUp();
      });
      row.appendChild(giveUpBtn);

      // Got a Ride! — active while paused too (EXP-013's cancel-dialog "Got a
      // ride" branch already resumes-then-gotRide for exactly this case; this
      // button used to be the one place in the whole flow where that same
      // outcome was unreachable in one tap). Resuming first means the wait
      // this leg reports is measured up to now, not silently frozen at the
      // pause point — the same reasoning gotRide's own wait_min already
      // relies on elsewhere.
      const gotRideBtn = document.createElement("button");
      gotRideBtn.className = "inr-big inr-big--green";
      gotRideBtn.innerHTML = '<i class="fa-solid fa-thumbs-up"></i> ' + T("Got a Ride!");
      gotRideBtn.addEventListener("click", function () {
        journeyFlow.resume();
        journeyUI.rideDetailsSheet(function (details) {
          journeyFlow.gotRide(details);
        });
      });
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
      label.textContent = T("In a ride · {time}", { time: fmtHMS(Date.now() - j.gotRideMs) });
      chip.appendChild(label);

      document.body.appendChild(chip);
      journeyUI._chipEl = chip;

      journeyUI._tickInterval = setInterval(function () {
        const cur = journeyStore.get();
        if (cur && cur.gotRideMs) {
          label.textContent = T("In a ride · {time}", { time: fmtHMS(Date.now() - cur.gotRideMs) });
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
      finishBtn.innerHTML = '<i class="fa-solid fa-flag-checkered"></i> ' + T("Finish Ride");
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
        ? '<i class="fa-solid fa-check"></i> ' + T("Details complete")
        : '<i class="fa-solid fa-plus"></i> ' + T("Add details · {pct}%", { pct: s.pct });
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

      // Lift the timer chip clear of the WHOLE dock. The chip is a separately
      // positioned fixed pill; the in-ride dock's height is not constant (the
      // "Add details" label wraps on narrow screens, button metrics differ), so a
      // fixed CSS offset (the old +124px) kept landing the chip on top of the
      // Add-details bar and the Finish button. Derive the chip's bottom from the
      // dock's actual rendered box after layout so it always clears it. rAF: the
      // dock must be laid out before getBoundingClientRect returns its height.
      requestAnimationFrame(function () {
        if (!journeyUI._chipEl || !journeyUI._dockEl) return; // torn down meanwhile
        const dockBottom = parseFloat(getComputedStyle(dock).bottom) || 0;
        chip.style.bottom = dockBottom + dock.getBoundingClientRect().height + 10 + "px";
      });
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
        ? '<i class="fa-solid fa-spinner fa-spin"></i> ' + T("Saving…")
        : '<i class="fa-solid fa-flag-checkered"></i> ' + T("Finish Ride");
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

    // Unified draggable-pin confirm step. Replaces the two near-identical pickers this
    // file used to carry (manualPin for the drop-off, setWaitingSpot for the next waiting
    // spot) — which had DIFFERENT coordinate output contracts, a mismatch that once
    // shipped destination_lon: undefined to the backend. onConfirm ALWAYS gets {lat, lon}.
    //
    // We cannot reuse setupLocationSelection() from map.js: its confirmLocationSelection()
    // writes to sessionStorage and then does window.location.href = "/ride" — a redirect
    // that would exit the in-ride flow entirely.
    //
    // opts:
    //   title, hint, confirmLabel — card copy (developer constants, not user input)
    //   seed       {lat, lon} | null — initial pin position; null → current map centre
    //   color      "orange" (drop-off) | "green" (waiting spot)
    //   autoLocate bool — request GPS in the background and snap the pin if untouched
    //   myLocation bool — show the "Use my location" button
    //   onConfirm(dest {lat, lon})
    //   onCancel() — optional
    //   onOutcome(name, details) — optional, aggregate analytics only
    pinConfirm(opts) {
      if (!window.L || !window.map) {
        // No map available (edge case) — never leave the Finish button spinning.
        journeyUI.setFinishBusy(false);
        return;
      }
      // Never stack two pin pickers: a second card would reuse the same button ids and
      // steal the first card's Confirm/Cancel wiring, leaving the visible buttons dead.
      if (journeyUI._picking) return;
      journeyUI._picking = true;

      const c = window.map.getCenter();
      const seed = opts.seed || { lat: c.lat, lon: c.lng };

      const marker = L.marker([seed.lat, seed.lon], {
        draggable: true,
        icon: L.icon({
          iconUrl: "/static/markers/marker-icon-2x-" + (opts.color || "orange") + ".png",
          shadowUrl: "/static/markers/marker-shadow.png",
          iconSize: [25, 41], iconAnchor: [12, 41],
          popupAnchor: [1, -34], shadowSize: [41, 41],
        }),
      }).addTo(window.map);

      // Once the user has placed the pin themselves, a late GPS fix must never move it —
      // a fix can land 20 s after the picker opens, long after they dragged the pin.
      let touched = false;
      let placement = opts.seed ? "seed" : "map-centre";
      function touch(method) { touched = true; placement = method; }
      marker.on("dragstart", function () { touch("drag"); });

      // Tapping the map also repositions the pin (same UX as the standard
      // location-selection UI in map.js).
      function onMapClick(e) { touch("map-tap"); marker.setLatLng(e.latlng); }
      window.map.on("click", onMapClick);

      // Expose a reposition hook so a long-press (routed through inrideOnEntryGesture)
      // can drop the pin too — but ONLY while this picker is open, so long-press never
      // drops a pin outside the flow.
      journeyUI._setPin = function (ll) { touch("long-press"); marker.setLatLng(ll); };

      const ui = document.createElement("div");
      ui.className = "location-selection-ui";
      ui.innerHTML = [
        "<h4>" + opts.title + "</h4>",
        "<p>" + opts.hint + "</p>",
        '<div class="lsel-actions">',
        // "Use my location" is a positive/neutral action — give it confirm styling so it
        // doesn't read as a dismiss button; only Cancel gets the muted lsel-cancel style.
        opts.myLocation ? '<button class="lsel-confirm" id="inr-pin-myloc">' + T("Use my location") + "</button>" : "",
        '<button class="lsel-confirm" id="inr-pin-confirm">' + opts.confirmLabel + "</button>",
        '<button class="lsel-cancel" id="inr-pin-cancel">' + T("Cancel") + "</button>",
        "</div>",
      ].join("");
      document.body.appendChild(ui);
      // While dropping the pin, neutralize overlay markers (e.g. Hitchwiki event
      // pins) so a stray tap on one repositions the pin instead of opening its
      // sheet and swallowing the click. See body.inr-picking rule in style.css.
      document.body.classList.add("inr-picking");

      // One geolocation request shared by the background autoLocate and the button, so
      // tapping "Use my location" mid-flight never starts a second fix.
      let fixPromise = null;
      function requestFix() {
        if (!fixPromise) {
          fixPromise = getFixWithRetry();
          // Drop a failed fix so an explicit tap retries instead of replaying the
          // cached rejection.
          fixPromise.catch(function () { fixPromise = null; });
        }
        return fixPromise;
      }

      const locBtn = document.getElementById("inr-pin-myloc");
      function setLocating(on) {
        if (!locBtn) return;
        locBtn.disabled = on;
        locBtn.textContent = on ? T("Locating…") : T("Use my location");
      }

      function moveTo(fix) {
        marker.setLatLng([fix.lat, fix.lon]);
        window.map.setView([fix.lat, fix.lon]);
      }

      function outcome(name, details) {
        if (opts.onOutcome) opts.onOutcome(name, details || {});
      }

      if (opts.autoLocate) {
        setLocating(true);
        requestFix().then(
          function (fix) {
            setLocating(false);
            if (!touched) {
              placement = "auto-location";
              moveTo(fix);
              outcome("auto-location-used");
            } else {
              outcome("auto-location-ignored");
            }
          },
          // Silent: the user never asked for this fix, and the pin is already usable.
          function () { setLocating(false); outcome("auto-location-failed"); }
        );
      }

      if (locBtn) {
        locBtn.addEventListener("click", function () {
          setLocating(true);
          requestFix().then(
            function (fix) {
              setLocating(false);
              touch("location-button");
              moveTo(fix);
              outcome("location-button-used");
            },
            function () {
              setLocating(false);
              outcome("location-button-failed");
              journeyUI.error(T("Couldn't get your location — drag the pin instead."));
            }
          );
        });
      }

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
        outcome("confirmed", { placement: placement });
        cleanup();
        // Normalize Leaflet's .lng → .lon so every consumer sees exactly one shape.
        opts.onConfirm(toLatLon(ll));
      });

      document.getElementById("inr-pin-cancel").addEventListener("click", function () {
        outcome("cancelled", { placement: placement });
        cleanup();
        if (opts.onCancel) opts.onCancel();
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
      closeX.setAttribute("aria-label", T("Close"));
      closeX.innerHTML = "&times;";
      closeX.addEventListener("click", function () { close(); });
      sheet.appendChild(closeX);

      // Title
      const titleEl = document.createElement("h4");
      titleEl.textContent = T("How was the spot?");
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
      vehicleLabel.textContent = T("Who picked you up?");
      vehicleField.appendChild(vehicleLabel);
      const vehicleChipsEl = document.createElement("div");
      vehicleChipsEl.className = "inr-chips";
      [
        { code: "car",   label: "🚗 " + T("Car")   },
        { code: "truck", label: "🚚 " + T("Truck") },
        { code: "van",   label: "🚐 " + T("Van")   },
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
      signalLabel.textContent = T("How did you signal?");
      signalField.appendChild(signalLabel);
      const signalChipsEl = document.createElement("div");
      signalChipsEl.className = "inr-chips";
      [
        { code: "thumb", label: "👍 " + T("Thumb")  },
        { code: "sign",  label: "📝 " + T("Sign")   },
        { code: "ask",   label: "🗣 " + T("Asking") },
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
      commentLabel.textContent = T("Comment (optional)");
      commentField.appendChild(commentLabel);
      const textarea = document.createElement("textarea");
      textarea.className = "inr-sheet__textarea";
      textarea.placeholder = T("Anything worth noting about this spot…");
      commentField.appendChild(textarea);
      // Licensing notice: comment + username are published under CC BY-SA 4.0 (the
      // database as a whole is ODbL). Keep users aware of what they agree to on submit.
      const licenseNote = document.createElement("p");
      licenseNote.className = "inr-sheet__license";
      licenseNote.style.cssText = "font-size:11px;color:#999;margin:4px 0 0;line-height:1.4;";
      licenseNote.innerHTML = T("Published publicly. Your comment and username are licensed {ccbysa}; the database is {odbl}.", {
        ccbysa: '<a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noopener">CC BY-SA 4.0</a>',
        odbl: '<a href="https://opendatacommons.org/licenses/odbl/1-0/" target="_blank" rel="noopener">ODbL</a>',
      });
      commentField.appendChild(licenseNote);
      sheet.appendChild(commentField);

      // ── Ride On! CTA (green, disabled until rating chosen) ────────────────────
      const rideOnBtn = document.createElement("button");
      rideOnBtn.type = "button";
      rideOnBtn.className = "inr-big inr-big--green inr-sheet__save inr-disabled";
      rideOnBtn.disabled = true;
      rideOnBtn.innerHTML = '<i class="fa-solid fa-check"></i> ' + T("Ride On!");
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
      closeX.type = "button"; closeX.className = "inr-sheet__close"; closeX.setAttribute("aria-label", T("Close"));
      closeX.innerHTML = "&times;"; closeX.addEventListener("click", function () { close(); });
      sheet.appendChild(closeX);

      const titleEl = document.createElement("h4"); titleEl.textContent = T("Driver & vehicle details"); sheet.appendChild(titleEl);

      // ── Two tabs (Driver / Vehicle), each a fill-bar of its own section's
      //    completeness. Only the active panel shows; the fill bars update live. ──
      const tabbar = document.createElement("div"); tabbar.className = "inr-tabbar";
      const driverPanel = document.createElement("div"); driverPanel.className = "inr-tabpanel";
      const vehiclePanel = document.createElement("div"); vehiclePanel.className = "inr-tabpanel";
      const driverTab = makeTab(T("Driver")); const vehicleTab = makeTab(T("Vehicle"));
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
        input.placeholder = T("License plate code (e.g. D, F, GB)…"); input.setAttribute("autocomplete", "off");
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
        input.placeholder = T("Type a language…"); input.setAttribute("autocomplete", "off");
        const list = document.createElement("ul"); list.className = "inr-cohitch-suggest"; list.style.display = "none";
        wrap.appendChild(tags); wrap.appendChild(input); wrap.appendChild(list); w.appendChild(wrap);
        function nameFor(code) { const p = choices.find(function (c) { return c[0] === code; }); return p ? p[1] : code; }
        function renderTags() {
          tags.innerHTML = "";
          arr.forEach(function (code) {
            const t = document.createElement("span"); t.className = "inr-tag"; t.textContent = nameFor(code);
            const x = document.createElement("button"); x.type = "button"; x.className = "inr-tag__x"; x.setAttribute("aria-label", T("Remove")); x.innerHTML = "&times;";
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
      const reasonF = fieldWrap(T("Why did they pick you up?")); chipMulti(reasonF, ch.reasons, f.driver_reason_to_pick_up); driverPanel.appendChild(reasonF);
      const genderF = fieldWrap(T("Driver gender")); chipSingle(genderF, ch.genders, function () { return f.driver_gender; }, function (v) { f.driver_gender = v; }); driverPanel.appendChild(genderF);
      const ageF = fieldWrap(T("Approx. driver age"));
      const ageHelp = document.createElement("div"); ageHelp.className = "inr-field__help"; ageHelp.textContent = T("A rough guess is fine."); ageF.appendChild(ageHelp);
      const age = document.createElement("input"); age.type = "number"; age.min = "0"; age.max = "120"; age.className = "inr-cohitch-input"; age.inputMode = "numeric";
      if (f.driver_age !== "") age.value = f.driver_age;
      age.addEventListener("input", function () { f.driver_age = age.value === "" ? "" : parseInt(age.value, 10); refreshMeters(); });
      ageF.appendChild(age); driverPanel.appendChild(ageF);
      const originF = fieldWrap(T("Driver's country")); searchSelect(originF, ch.countries, T("Search country…"), function () { return f.driver_origin_country; }, function (v) { f.driver_origin_country = v; }); driverPanel.appendChild(originF);
      const langF = fieldWrap(T("Languages spoken")); tagAutocomplete(langF, ch.languages, f.driver_languages); driverPanel.appendChild(langF);

      // ── Vehicle tab ──────────────────────────────────────────────────────────
      const kindF = fieldWrap(T("Vehicle"));
      chipSingle(kindF, ch.vehicle_kinds.map(function (p) { return [p[0], p[1] + " " + p[0]]; }), function () { return f.vehicle_kind; }, function (v) { f.vehicle_kind = v; });
      vehiclePanel.appendChild(kindF);
      const plateF = fieldWrap(T("Number-plate country")); plateSelect(plateF, ch.plate_countries, function () { return f.vehicle_license_plate_country; }, function (v) { f.vehicle_license_plate_country = v; }); vehiclePanel.appendChild(plateF);
      // make/model — passenger vehicles only, optional (not scored). Hidden for other kinds by refreshMeters().
      const makeModelWrap = document.createElement("div");
      const makeF = fieldWrap(T("Make (optional)")); const make = document.createElement("input"); make.type = "text"; make.className = "inr-cohitch-input"; make.value = f.vehicle_make; make.addEventListener("input", function () { f.vehicle_make = make.value; refreshMeters(); }); makeF.appendChild(make); makeModelWrap.appendChild(makeF);
      const modelF = fieldWrap(T("Model (optional)")); const model = document.createElement("input"); model.type = "text"; model.className = "inr-cohitch-input"; model.value = f.vehicle_model; model.addEventListener("input", function () { f.vehicle_model = model.value; refreshMeters(); }); modelF.appendChild(model); makeModelWrap.appendChild(modelF);
      vehiclePanel.appendChild(makeModelWrap);

      const saveBtn = document.createElement("button");
      saveBtn.type = "button"; saveBtn.className = "inr-big inr-big--green inr-sheet__save";
      saveBtn.innerHTML = '<i class="fa-solid fa-check"></i> ' + T("Save details");
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
      closeX.setAttribute("aria-label", T("Close"));
      closeX.innerHTML = "&times;";
      closeX.addEventListener("click", function () { close(); });
      sheet.appendChild(closeX);

      const titleEl = document.createElement("h4");
      titleEl.textContent = T("Anybody hitching with you");
      sheet.appendChild(titleEl);

      // Logged-in confirmation line ("You're hitching as @name"); omitted when anonymous.
      if (window.USERNAME) {
        const who = document.createElement("p");
        who.className = "inr-sheet__sub";
        who.textContent = T("You're hitching as @{username}", { username: window.USERNAME });
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
      input.placeholder = T("Add co-hitchhiker username…");
      const suggest = document.createElement("ul");
      suggest.className = "inr-cohitch-suggest";
      suggest.style.display = "none";
      inputWrap.appendChild(input);
      inputWrap.appendChild(suggest);
      field.appendChild(inputWrap);
      sheet.appendChild(field);

      // "Add anonymous" — a co-hitcher with no account. Multiple are allowed; the backend
      // turns each "Anonymous" entry in co_hitchhiker into an anonymous hitchhiker. The
      // gendered variants post "Anonymous:male" / "Anonymous:female" so the gender reaches
      // Nostr as that hitchhiker's `gender` (see publish_ride.py).
      const anonRow = document.createElement("div");
      anonRow.className = "inr-cohitch-anonrow";
      [
        { gender: "", label: T("Add anonymous") },
        { gender: "male", label: T("Anonymous ♂") },
        { gender: "female", label: T("Anonymous ♀") },
      ].forEach(function (opt) {
        const anonBtn = document.createElement("button");
        anonBtn.type = "button";
        anonBtn.className = "inr-cohitch-anon";
        anonBtn.innerHTML = '<i class="fa-solid fa-user-secret" aria-hidden="true"></i> ' + opt.label;
        anonBtn.addEventListener("click", function () { addAnonymous(opt.gender); });
        anonRow.appendChild(anonBtn);
      });
      sheet.appendChild(anonRow);

      // Chips show the gender as a symbol; the raw token is what's sent on submit.
      function chipLabel(name) {
        if (name === "Anonymous:male") return T("Anonymous ♂");
        if (name === "Anonymous:female") return T("Anonymous ♀");
        return name;
      }

      function renderChips() {
        chips.innerHTML = "";
        selected.forEach(function (name) {
          const chip = document.createElement("span");
          chip.className = "inr-cohitch-chip";
          chip.textContent = chipLabel(name);
          const x = document.createElement("button");
          x.type = "button";
          x.className = "inr-cohitch-chip__x";
          x.setAttribute("aria-label", T("Remove {name}", { name: chipLabel(name) }));
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

      function addAnonymous(gender) {
        // No account, so no username to dedupe/self-exclude — and multiple anonymous
        // co-hitchers are allowed (the backend counts each "Anonymous" entry).
        selected.push(gender ? "Anonymous:" + gender : "Anonymous");
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
      startBtn.innerHTML = '<i class="fa-solid fa-thumbs-up"></i> ' + T("Start hitching");
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
      closeX.setAttribute("aria-label", T("Close"));
      closeX.innerHTML = "&times;";
      closeX.addEventListener("click", function () { close(); });
      sheet.appendChild(closeX);

      const titleEl = document.createElement("h4");
      titleEl.textContent = T("How was the spot?");
      sheet.appendChild(titleEl);

      const subEl = document.createElement("p");
      subEl.className = "inr-sheet__sub";
      subEl.textContent = T("You waited here without a ride — rate the spot so others know.");
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
      commentLabel.textContent = T("Comment (optional)");
      commentField.appendChild(commentLabel);
      const textarea = document.createElement("textarea");
      textarea.className = "inr-sheet__textarea";
      textarea.placeholder = T("e.g. no traffic, bad pull-in spot…");
      commentField.appendChild(textarea);
      // Licensing notice: comment + username are published under CC BY-SA 4.0 (the
      // database as a whole is ODbL). Keep users aware of what they agree to on submit.
      const licenseNote = document.createElement("p");
      licenseNote.className = "inr-sheet__license";
      licenseNote.style.cssText = "font-size:11px;color:#999;margin:4px 0 0;line-height:1.4;";
      licenseNote.innerHTML = T("Published publicly. Your comment and username are licensed {ccbysa}; the database is {odbl}.", {
        ccbysa: '<a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noopener">CC BY-SA 4.0</a>',
        odbl: '<a href="https://opendatacommons.org/licenses/odbl/1-0/" target="_blank" rel="noopener">ODbL</a>',
      });
      commentField.appendChild(licenseNote);
      sheet.appendChild(commentField);

      // ── Save CTA (disabled until a rating is chosen) ──────────────────────────
      const saveBtn = document.createElement("button");
      saveBtn.type = "button";
      saveBtn.className = "inr-big inr-big--green inr-sheet__save inr-disabled";
      saveBtn.disabled = true;
      saveBtn.innerHTML = '<i class="fa-solid fa-check"></i> ' + T("Save");
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
        title: T("Add driver & vehicle details?"),
        body: T("This ride is {pct}% complete. Help your fellow hitchers?", { pct }),
        centered: true,
        forced: true,
        actions: [
          // "Add details" opens the details sheet (which closes this dialog via the
          // single-flight guard); its Save fires onAdd, which then continues the finish.
          { label: T("Add details"), cls: "inr-go", onClick: function () {
            journeyUI.detailsSheet(seed, function (fields) { onAdd(fields); });
          } },
          { label: T("Skip"), cls: "inr-grey", onClick: function () { onSkip(); } },
        ],
      });
    },

    // Forced would-ride-again gate on finish: a required Yes/No with no dismissal.
    // Deliberately NOT part of the completeness score — a per-ride sentiment we always
    // capture, independent of the demographic points.
    wouldRideAgainSheet(onAnswer) {
      journeyUI.dialog({
        title: T("Would you accept this ride again?"),
        body: T("One quick question before we save this ride."),
        centered: true,
        forced: true,
        actions: [
          { label: T("Yes"), cls: "inr-go",   onClick: function () { onAnswer(true); } },
          { label: T("No"),  cls: "inr-grey", onClick: function () { onAnswer(false); } },
        ],
      });
    },

    dialog({ title, body, actions, onClose, centered, forced, cancelButton }) {
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

      // reason distinguishes an explicit action button from a scrim tap (or a future
      // dismissal path) for callers that need to treat the two differently -- e.g. a
      // choice with a safe default should still apply it on an accidental scrim tap,
      // not just lose whatever the dialog was for. close() always runs *before* the
      // clicked button's own onClick (see below), so onClose cannot infer this from
      // execution order; it has to be told.
      function close(reason) {
        if (scrim.parentNode) scrim.parentNode.removeChild(scrim);
        if (card.parentNode) card.parentNode.removeChild(card);
        journeyUI._openDialog = null;
        // Fires on ANY dismissal (button or scrim tap) so callers can clean up
        // transient chrome they attached alongside the dialog (e.g. a preview pin).
        if (onClose) onClose(reason);
      }

      actions.forEach(function (action) {
        const btn = document.createElement("button");
        btn.className = action.cls;
        btn.textContent = action.label;
        btn.addEventListener("click", function () {
          close("button");
          action.onClick();
        });
        actionsEl.appendChild(btn);
      });

      card.appendChild(actionsEl);

      // Explicit way out for dialogs whose every button *does* something (the spot
      // menu: Start Hitching / Log a past ride / Propose a spot). A scrim tap already
      // dismisses, but that affordance is invisible, so the dialog read as inescapable.
      // Same round red × as the journey dock's Cancel, sitting below the actions.
      if (cancelButton && !forced) {
        const cancelBtn = document.createElement("button");
        cancelBtn.type = "button";
        cancelBtn.className = "inr-cancel";
        cancelBtn.setAttribute("aria-label", T("Close"));
        cancelBtn.innerHTML = '<i class="fa-solid fa-xmark" aria-hidden="true"></i>';
        cancelBtn.addEventListener("click", () => close("cancel-x"));
        card.appendChild(cancelBtn);
      }

      // Tap the scrim (outside the card) to cancel — unless the dialog is `forced`
      // (a required answer, e.g. would-ride-again on finish), where there is no way out
      // but the action buttons. Not passed directly as the listener: that would hand
      // close() the click MouseEvent as `reason` instead of a real one.
      if (!forced) scrim.addEventListener("click", () => close("scrim"));

      document.body.appendChild(scrim);
      document.body.appendChild(card);

      journeyUI._openDialog = { close };
      return { close };
    },
  };

  // ── Permanent contribution bar: "Start Hitchhiking" / "Log a past ride" ──────
  // Give Up / Got a Ride only exist once a journey is running, so the tracker had no
  // visible way in: you had to know about the map long-press or find a spot's "Hitch
  // here". The green half is on screen whenever no journey is active and opens the same
  // waiting-spot picker used after a drop-off ("Use my location" or drag/tap a pin),
  // then hands the confirmed point to the normal start flow — soft login gate,
  // co-hitchers, then the waiting dock with Give Up / Got a Ride.
  //
  // The grey half is the /ride form. Both are the same decision — "record a ride I'm
  // about to take" vs "record one I already took" — so they sit side by side as equal
  // halves instead of the form hiding in the bottom action pane, where it read as a
  // navigation item rather than the primary contribution path.
  //
  // It is mounted once and never removed: every "something else owns the bottom of the
  // screen" case is a CSS rule on #inr-start-bar (see style.css), so there is no
  // show/hide lifecycle to keep in sync with render/teardown. That includes the initial
  // load — the bar is `display: none` until map.js puts `.spots-loaded` on <body>,
  // since mounting happens as soon as window.map exists, long before the map is usable.
  const startLauncher = {
    _el: null,

    mount() {
      if (startLauncher._el) return;
      // Deployments that hide the contribution entry points must not get a second
      // one back through the journey tracker.
      if (window.HIDE_ADD_SPOT_BUTTON) return;

      const bar = document.createElement("div");
      bar.id = "inr-start-bar";
      bar.className = "inr-split";

      const btn = document.createElement("button");
      btn.type = "button";
      btn.id = "inr-start-btn";
      // Same classes as the dock buttons so both halves inherit their shape/weight/
      // shadow; the bar rule only tightens the padding for the narrower halves.
      btn.className = "inr-big inr-big--green";
      // fa-thumbs-up is already this app's "start hitching" icon (spot sheet's
      // "Hitch here"); it never shares the screen with the Got a Ride! button.
      btn.innerHTML = '<i class="fa-solid fa-thumbs-up" aria-hidden="true"></i> ' + T("Start Hitchhiking");
      btn.addEventListener("click", startLauncher.open);

      const past = document.createElement("button");
      past.type = "button";
      past.id = "inr-log-past-btn";
      past.className = "inr-big inr-big--green-light";
      // The 🚗💨 the bottom action pane used for "Add your ride", desaturated: it keeps
      // that entry point recognisable while staying visually secondary to the green half.
      past.innerHTML = '<span class="inr-emoji-bw" aria-hidden="true">🚗💨</span> ' + T("Log a past ride");
      past.addEventListener("click", function () {
        // Same funnel step the bottom action pane used to report, so the
        // add_ride_clicked → ride_form_submitted drop-off stays comparable.
        hmTrack("add_ride_clicked", { source: "start-bar" });
        window.location.href = "/ride";
      });

      bar.appendChild(btn);
      bar.appendChild(past);
      document.body.appendChild(bar);
      // Same reason as the dock/chip: without this a tap falls through to Leaflet and
      // opens whatever spot sits under the bar.
      sealTaps(bar);
      startLauncher._el = bar;
      // The bottom-right map controls are lifted clear of this bar in CSS, which needs
      // its height — and the height is not a constant: the labels wrap to two lines on
      // a narrow screen and reflow when the web font lands. Publish the measured value
      // instead of hardcoding one.
      startLauncher._trackHeight(bar);
      // Lets CSS lift the map controls only where the bar actually exists (a
      // HIDE_ADD_SPOT_BUTTON deployment returns above and never gets here).
      document.body.classList.add("has-start-bar");
    },

    _trackHeight(bar) {
      const publish = () => {
        const h = bar.getBoundingClientRect().height;
        // Skip 0: the bar is display:none until spots load, and writing 0 would drop
        // the map controls back onto it for that window.
        if (h > 0) document.documentElement.style.setProperty("--inr-start-bar-h", h + "px");
      };
      publish();
      // Fires on the display:none → visible transition too, so the var is right from
      // the first frame the bar is on screen.
      if (window.ResizeObserver) new ResizeObserver(publish).observe(bar);
      else window.addEventListener("resize", publish);
    },

    // Opens the same waiting-spot picker used after a drop-off.
    open() {
      if (journeyStore.get()) return; // one journey at a time
      if (document.body.classList.contains("inr-picking")) return; // picker already open
      if (!window.map) return;
      hmTrack("journey_start_button_clicked", {});
      journeyUI.pinConfirm({
        title: T("Where are you waiting?"),
        hint: T("Drag the pin or tap the map, then confirm."),
        confirmLabel: T("Confirm"),
        // Seeded at the map centre so the picker has something to show immediately;
        // "Use my location" and dragging stay available regardless.
        seed: null,
        color: "green",
        // Geolocation is never requested on page load (see map.js), so the map centre
        // at the moment this button is tapped is not the user's location — it's
        // whatever view they happened to be on (a spot they were checking, a
        // last-viewed hash, a default region). Unlike the "Wait somewhere else" picker,
        // there is no just-confirmed point to seed from here, so a silent background
        // fix is worth it: same pattern as "Confirm Drop-off" below, non-blocking and
        // silent on denial/failure, only moves the pin if the user hasn't touched it.
        autoLocate: true,
        myLocation: true,
        onOutcome: function (outcome, details) {
          hmTrack("journey_start_picker", Object.assign({ outcome: outcome }, details));
        },
        onConfirm: (latlng) => journeyFlow.startFromChoose(latlng, "start-bar"),
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
      title: T("This spot"),
      body: T("Track a ride from here now — or log a ride you already got."),
      onClose: () => { if (previewPin && window.map) window.map.removeLayer(previewPin); previewPin = null; },
      // Every action here commits to a flow, so the dialog needs a visible dismiss.
      cancelButton: true,
      actions: [
        {
          label: T("Start Hitching"),
          cls: "inr-go",
          onClick: () => journeyFlow.startFromChoose(latlng, "map-gesture"),
        },
        {
          label: T("Log a past ride"),
          cls: "inr-ghost",
          // Reuses the existing add-spot flow unchanged; only the label differs.
          onClick: () => window.startAddSpotFromGesture(latlng, containerPoint),
        },
        {
          label: T("Propose a spot"),
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
        ? '<i class="fa-solid fa-triangle-exclamation"></i> ' + T("{n} to upload", { n: all.length })
        : '<i class="fa-solid fa-rotate"></i> ' + T("{n} to upload", { n: all.length });
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
        titleEl.textContent = T("Rides to upload");
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
          const kindLabel = it.kind === "giveup" ? T("Gave up") : T("Ride");
          const strong = document.createElement("strong");
          strong.textContent = kindLabel;
          info.appendChild(strong);
          info.appendChild(document.createTextNode(" · " + T("{age} ago", { age: outboxUI._age(it.createdAt) })));
          info.appendChild(document.createElement("br"));
          const statusEl = document.createElement("span");
          if (it.status === "failed") {
            statusEl.className = "inr-outbox-row__err";
            statusEl.textContent = T("Couldn't save: {error}", { error: it.lastError || "rejected" });
          } else {
            statusEl.className = "inr-outbox-row__wait";
            statusEl.textContent = T("Waiting for connection…");
          }
          info.appendChild(statusEl);
          row.appendChild(info);

          const actions = document.createElement("div");
          actions.className = "inr-outbox-row__actions";

          // Details → view/edit the queued ride (rating, comment, timestamps) before upload.
          const details = document.createElement("button");
          details.type = "button";
          details.className = "inr-outbox-row__btn";
          details.title = T("Details / edit");
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
          del.title = T("Delete");
          del.innerHTML = '<i class="fa-solid fa-trash"></i>';
          del.addEventListener("click", function () {
            if (window.confirm(T("Delete this ride? It won't be uploaded."))) {
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
          retry.innerHTML = '<i class="fa-solid fa-rotate"></i> ' + T("Retry now");
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
        closeBtn.textContent = T("Close");
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
      titleEl.textContent = item.kind === "giveup" ? T("Gave-up spot") : T("Ride details");
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
        field(T("Picked up"), departureInput);
      }
      if (body.arrival_datetime) {
        arrivalInput = document.createElement("input");
        arrivalInput.type = "datetime-local";
        arrivalInput.className = "inr-input";
        arrivalInput.value = body.arrival_datetime;
        field(T("Arrived"), arrivalInput);
      }

      // ── Wait (minutes) ──
      const waitInput = document.createElement("input");
      waitInput.type = "number";
      waitInput.min = "0";
      waitInput.className = "inr-input";
      waitInput.value = body.wait || "0";
      field(T("Wait (minutes)"), waitInput);

      // ── Comment ──
      const textarea = document.createElement("textarea");
      textarea.className = "inr-sheet__textarea";
      textarea.value = body.comment || "";
      field(T("Comment (optional)"), textarea);

      // Read-only coordinates for reference.
      const coords = document.createElement("p");
      coords.className = "inr-sheet__sub";
      const hasDest = body.destination_lat !== "" && body.destination_lat != null;
      coords.textContent = T("From {from}", { from: Number(body.pickup_lat).toFixed(4) + ", " + Number(body.pickup_lon).toFixed(4) }) +
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
      saveBtn.innerHTML = '<i class="fa-solid fa-check"></i> ' + T("Save changes");
      saveBtn.addEventListener("click", function () {
        if (!rating) { errEl.textContent = T("Please choose a rating."); errEl.style.display = ""; return; }
        // Backend asserts arrival > departure when both present — validate here so an edit
        // can't push the item into a permanent 400.
        if (departureInput && arrivalInput && departureInput.value && arrivalInput.value &&
            arrivalInput.value <= departureInput.value) {
          errEl.textContent = T("Arrival must be after the pickup time."); errEl.style.display = ""; return;
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
      cancelBtn.textContent = T("Cancel");
      cancelBtn.addEventListener("click", close);
      sheet.appendChild(cancelBtn);

      scrim.addEventListener("click", close);
      document.body.appendChild(scrim);
      document.body.appendChild(sheet);
      journeyUI._openDialog = { close };
    },
  };

  // ── raceBanner: announce a currently-running named race, if any ─────────────
  // races.py already ranks hitchhikers automatically by matching their logged rides
  // against a race's city-pair + date window (RACES.md) — no comment tag, no organizer
  // relay required for the standings themselves. The gap this closes is discovery:
  // nothing on the map tells someone hitchhiking through a live race's corridor that a
  // leaderboard exists for what they're doing right now, so the only way anyone finds
  // out is an organizer telling their group — a channel with a poor track record (ask
  // it to prompt logging every year, it doesn't happen). This reaches participants
  // directly instead, keyed off RACES.md's own dates, so it works for any future named
  // race added there with no further code change.
  //
  // Deliberately not geo-targeted (no GPS permission prompt for a low-stakes banner) —
  // it shows to every visitor during the race window, not just people near the route.
  // That's over-broad by design: the false-positive cost (someone not racing sees a
  // one-time dismissible dialog) is far lower than the false-negative cost (a racer
  // near the corridor never learns the leaderboard exists).
  const raceBanner = {
    _shownKey(title) { return "hmRaceBannerShown:" + title; },

    async check() {
      // Don't compete with an active journey or an already-open dialog — the in-ride
      // tracker's own prompts (soft login gate, stale-journey welcome back) take
      // priority over this.
      if (journeyStore.get() || journeyUI._openDialog) return;
      let races;
      try {
        const res = await fetch("/races.json");
        if (!res.ok) return;
        races = await res.json();
      } catch (e) { return; } // offline, blocked, or missing — never block the map over this
      if (!Array.isArray(races)) return;
      const now = Date.now();
      const running = races.filter(function (r) {
        if (!r.name) return false; // organizer-named events only, not open-ended "virtual races"
        const from = Date.parse(r.from), to = Date.parse(r.to);
        // `to` is a bare YYYY-MM-DD (parses as that day's UTC midnight); +24h covers
        // the whole final day so a race doesn't read as over at its own start-of-day.
        return from && to && now >= from && now <= to + 24 * 3600 * 1000;
      });
      if (!running.length) return;
      // One race per *event name*, in case it has several legs (Tramprennen has two
      // starting cities) — pick the first leg not yet shown; seen[] also blocks a
      // later leg of the same event once any leg has already been shown once.
      const seen = {};
      const race = running.find(function (r) {
        if (seen[r.name]) return false;
        seen[r.name] = true;
        return !localStorage.getItem(raceBanner._shownKey(r.title));
      });
      if (!race) return;
      localStorage.setItem(raceBanner._shownKey(race.title), "1");
      hmTrack("race_banner_shown", { race: race.name });
      journeyUI.dialog({
        title: T("{name} is on right now", { name: race.name }),
        body: T(
          "Through {to}. Log your rides as you go and you'll show up automatically on the live leaderboard — no tag or special step needed. Mentioning \"{name}\" in your ride comment also helps us see how many racers are logging.",
          { to: race.to, name: race.name }
        ),
        centered: true,
        cancelButton: true,
        actions: [
          {
            label: T("See the leaderboard"),
            cls: "inr-go",
            onClick: function () {
              hmTrack("race_banner_leaderboard_clicked", { race: race.name });
              window.location.href = "/races";
            },
          },
          { label: T("Not now"), cls: "inr-grey", onClick: function () {} },
        ],
      });
    },
  };

  // ── thinCoverageBanner: ask someone physically in a documented gap to write it ──
  // Till (hitchhiking-automation PR#27): "1 build geolocation" — trigger from the
  // visitor's real position, not a viewport pan (over-broad) and not a just-logged
  // ride (the cheaper design a prior run built; that patch stays unshipped).
  //
  // Does NOT request geolocation on page load when the permission is still "prompt"
  // — map.js's locate button is the only place that asks. On load we only reuse an
  // already-granted permission (returning visitors). A locate-button fix also
  // calls onFix() so a first-time grant still reaches this the moment they tap GPS.
  // 40 km radius around each place's real coordinate, not the 3° grid cell the
  // scoping research used for ranking (those labels don't bound the towns).
  // 2026-08-23: the 36 France/Poland/Latvia/Estonia/Romania/Moldova targets added
  // 2026-08-22 all went stale the same day -- this repo published wiki stubs for
  // every one of them a few hours later, so the "write this missing article"
  // banner was pointing GPS-triggered visitors at articles that already existed.
  // Re-verified each of the 36 live against the wiki API (all now exist, 0
  // false negatives) and replaced them with the only remaining candidates from
  // the same screening pass (research/hitchwiki-remaining-countries-screened-
  // 2026-08-22.json) that are still genuinely unwritten: Colombia/Ecuador/Moldova
  // towns with >=5 rides/50km (below that the town has ~no logged hitchhiker
  // traffic, so the GPS trigger would essentially never fire anyway). Egypt/
  // Pakistan/Tanzania entries in that same file stayed excluded -- 0-1
  // rides/50km, same reasoning. Before reusing a target list built by a
  // different run, re-check titles against the API; don't assume "found
  // missing" stays true past the run that found it.
  const THIN_COVERAGE_TARGETS = [
    {
      id: "dingle",
      lat: 52.1408, lon: -10.2687, radiusKm: 40,
      title: "Dingle",
      url: "https://hitchwiki.org/en/index.php?title=Dingle&action=edit",
    },
    {
      id: "lahinch",
      lat: 52.9321, lon: -9.3459, radiusKm: 40,
      title: "Lahinch",
      url: "https://hitchwiki.org/en/index.php?title=Lahinch&action=edit",
    },
    {
      id: "la-estrella",
      lat: 6.1576781, lon: -75.6433878, radiusKm: 40,
      title: "La Estrella",
      url: "https://hitchwiki.org/en/index.php?title=La_Estrella&action=edit",
    },
    {
      id: "puerto-lopez",
      lat: -1.5440814, lon: -80.744524, radiusKm: 40,
      title: "Puerto Lopez",
      url: "https://hitchwiki.org/en/index.php?title=Puerto_Lopez&action=edit",
    },
    {
      id: "rezina",
      lat: 47.7489209, lon: 28.9565739, radiusKm: 40,
      title: "Rezina",
      url: "https://hitchwiki.org/en/index.php?title=Rezina&action=edit",
    },
    {
      id: "santa-elena",
      lat: -2.1954593, lon: -80.5669167, radiusKm: 40,
      title: "Santa Elena",
      url: "https://hitchwiki.org/en/index.php?title=Santa_Elena&action=edit",
    },
    {
      id: "latacunga",
      lat: -0.9340311, lon: -78.6145758, radiusKm: 40,
      title: "Latacunga",
      url: "https://hitchwiki.org/en/index.php?title=Latacunga&action=edit",
    },
    {
      id: "puyo",
      lat: -1.4854777, lon: -77.9969666, radiusKm: 40,
      title: "Puyo",
      url: "https://hitchwiki.org/en/index.php?title=Puyo&action=edit",
    },
    {
      id: "zipaquirá",
      lat: 5.0234748, lon: -74.0039818, radiusKm: 40,
      title: "Zipaquirá",
      url: "https://hitchwiki.org/en/index.php?title=Zipaquir%C3%A1&action=edit",
    },
    {
      id: "arjona",
      lat: 10.2534632, lon: -75.3427213, radiusKm: 40,
      title: "Arjona",
      url: "https://hitchwiki.org/en/index.php?title=Arjona&action=edit",
    },
  ];

  function thinCoverageHaversineKm(lat1, lon1, lat2, lon2) {
    const R = 6371;
    const toRad = function (d) { return (d * Math.PI) / 180; };
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  function findThinCoverageTarget(lat, lon) {
    if (typeof lat !== "number" || typeof lon !== "number" || isNaN(lat) || isNaN(lon)) return null;
    let best = null;
    let bestDist = Infinity;
    THIN_COVERAGE_TARGETS.forEach(function (target) {
      const d = thinCoverageHaversineKm(lat, lon, target.lat, target.lon);
      if (d <= target.radiusKm && d < bestDist) {
        best = target;
        bestDist = d;
      }
    });
    return best;
  }

  const thinCoverageBanner = {
    _shownKey(id) { return "hmThinCoverageShown:" + id; },

    onFix(lat, lon) {
      if (journeyStore.get() || journeyUI._openDialog) return;
      const target = findThinCoverageTarget(lat, lon);
      if (!target) return;
      if (localStorage.getItem(thinCoverageBanner._shownKey(target.id))) return;
      localStorage.setItem(thinCoverageBanner._shownKey(target.id), "1");
      hmTrack("thin_coverage_nudge_shown", { target: target.id, trigger: "geolocation" });
      journeyUI.dialog({
        title: T("{place} has no Hitchwiki article yet", { place: target.title }),
        body: T(
          "You're near {place}. A few lines about how to hitch out of town helps the next person who stands here.",
          { place: target.title }
        ),
        centered: true,
        cancelButton: true,
        actions: [
          {
            label: T("Write about {place}", { place: target.title }),
            cls: "inr-go",
            onClick: function () {
              hmTrack("thin_coverage_nudge_clicked", { target: target.id, trigger: "geolocation" });
              window.open(target.url, "_blank", "noopener");
            },
          },
          { label: T("Not now"), cls: "inr-grey", onClick: function () {} },
        ],
      });
    },

    check() {
      if (journeyStore.get() || journeyUI._openDialog) return;
      if (!navigator.geolocation) return;
      const useGranted = function () {
        navigator.geolocation.getCurrentPosition(
          function (pos) {
            thinCoverageBanner.onFix(pos.coords.latitude, pos.coords.longitude);
          },
          function () { /* denied/timeout/unavailable — never alert, never block the map */ },
          { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 }
        );
      };
      if (navigator.permissions && navigator.permissions.query) {
        navigator.permissions.query({ name: "geolocation" }).then(function (status) {
          if (status.state === "granted") useGranted();
        }).catch(function () { /* Permissions API can throw on some WebViews; skip */ });
        return;
      }
      // No Permissions API: don't call getCurrentPosition — that would prompt on load.
    },
  };

  window.inride = {
    journeyStore, journeyUI, journeyFlow, outboxStore, submitBody, flushOutbox, outboxUI, startLauncher,
    journeyLogStore, pendingTripStore, finalizeJourney, tryCreateTrip, rideFactsFromBody, raceBanner,
    thinCoverageBanner,
  };

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
    // Mount first and unconditionally: every early return below leaves a state in which
    // the launcher is either wanted (no journey) or hidden by CSS (journey active /
    // dialog open), so it must exist in the DOM before any of them can be taken.
    startLauncher.mount();

    // Complete the login round-trip: the "Log in" button stashed the chosen spot in
    // PENDING_KEY before redirecting; on return we pick it up and start the journey.
    const pend = localStorage.getItem(PENDING_KEY);
    if (pend && window.IS_LOGGED_IN) {
      localStorage.removeItem(PENDING_KEY);
      // return is INSIDE the try so a malformed PENDING_KEY that throws falls through
      // to the store-resume path below instead of short-circuiting the whole init.
      try {
        const p = JSON.parse(pend);
        journeyFlow.beginWithCoHitchers({ lat: p.lat, lon: p.lon }, startSource(p.source));
        return;
      } catch (e) {}
    } else if (pend) {
      // Returned still anonymous (login cancelled or failed) — discard the stash.
      localStorage.removeItem(PENDING_KEY);
    }

    // Non-blocking load of score weights and driver-info choices so the in-ride sheet
    // can render and score synchronously once the user reaches the demographics step.
    loadDemographicData();

    // Non-blocking; the check itself skips out if a journey is already active or
    // another dialog is already open, so call order relative to the rest of this
    // function doesn't matter. Thin-coverage waits for the race banner's fetch so
    // the two dialogs never race; thinCoverageBanner.check also no-ops if a
    // dialog opened in the meantime.
    raceBanner.check().then(function () { thinCoverageBanner.check(); });

    const j = journeyStore.get();
    if (!j) return;

    // Old-journey affordance: if the current segment's anchor is > 24 h old, offer
    // Resume (restore as-is) or Discard before drawing the timer and dock, so the
    // user isn't silently dropped into a stale journey after overnight or longer.
    if (Date.now() - lastActiveMs(j) > STALE_MS) {
      journeyUI.dialog({
        title: T("Welcome back!"),
        body: T("You have a hitching journey from more than 24 hours ago. Continue where you left off?"),
        actions: [
          { label: T("Resume"),  cls: "inr-go", onClick: function () { journeyUI.render(j); } },
          { label: T("Discard"), cls: "inr-grey",    onClick: function () { journeyFlow.discard(); } },
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

  // Reconnect → drain immediately (don't wait for the interval), and retry a trip whose
  // POST itself was what failed (its rides may already be uploaded).
  window.addEventListener("online", function () { flushOutbox(); tryCreateTrip(); });

  // On load: restore the chip and, if a previous session left queued rides, flush + tick.
  function initOutbox() {
    outboxUI.refresh();
    if (outboxStore.pending().length) { flushOutbox(); startOutboxTimer(); }
    // A journey finished on a previous visit may still owe its trip — either its rides
    // were queued then, or the grouping POST never got through.
    tryCreateTrip();
  }

  // Run only after Leaflet's window.map is ready — _renderInRide places a Leaflet marker
  // and needs the map instance to exist first. Poll at 100 ms; interval clears itself.
  if (window.map) { initInride(); initOutbox(); }
  else { const t = setInterval(function () { if (window.map) { clearInterval(t); initInride(); initOutbox(); } }, 100); }
})();
