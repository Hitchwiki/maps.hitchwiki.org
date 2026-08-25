// End-of-journey behaviour in inride.js: the success overlay for the last ride logged,
// and the auto-grouped trip a multi-ride journey queues.
//
// inride.js is a browser IIFE, so it is loaded the way CLAUDE.md describes for
// routing.js: stub the browser globals, eval the file, then drive window.inride. The
// flows are called directly rather than clicked through, since the DOM stub is nowhere
// near complete enough to render the dock.

const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const RideSubmit = require("../hitch/static/ride_submit.js");
const SOURCE = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "inride.js"), "utf8");

function memoryStorage() {
  const data = new Map();
  return {
    getItem: (k) => (data.has(k) ? data.get(k) : null),
    setItem: (k, v) => data.set(k, String(v)),
    removeItem: (k) => data.delete(k),
  };
}

// A world just complete enough to evaluate the module and call its flows. Leaving
// window.map unset keeps the on-load init (which does need a real DOM) from running.
const loaded = [];
test.after(() => loaded.forEach((stop) => stop()));

function loadInride({ online = true, loggedIn = false, fetchImpl = null, storage = null } = {}) {
  const overlays = [];
  const trips = [];
  const fetches = [];
  // Real timers, so the d-tag poll can actually settle — but every handle is tracked and
  // cleared by stop(). The module arms a 100 ms poll waiting for window.map (which is
  // never set here), which would otherwise keep the test process alive forever.
  const timers = new Set();

  const window = {
    RideSubmit,
    IS_LOGGED_IN: loggedIn,
    hmTrack: () => {},
    addEventListener: () => {},
    location: { origin: "https://maps.example", hash: "", search: "" },
    // The two map.js entry points inride.js calls into.
    showPostSubmitOverlay: (kind, opts) => overlays.push({ kind, opts }),
    showTripCreated: (trip) => trips.push(trip),
  };
  const sandbox = {
    window,
    self: window,
    document: { addEventListener: () => {}, createElement: () => ({ style: {}, classList: { add() {}, remove() {} } }), body: { classList: { add() {}, remove() {} } } },
    localStorage: storage || memoryStorage(),
    sessionStorage: memoryStorage(),
    navigator: { onLine: online, geolocation: {} },
    console,
    setInterval: (fn, ms) => {
      const t = setInterval(fn, ms);
      timers.add(t);
      return t;
    },
    clearInterval: (t) => {
      timers.delete(t);
      clearInterval(t);
    },
    setTimeout: () => 0,
    clearTimeout: () => {},
    Promise,
    Set,
    Map,
    JSON,
    Date,
    Math,
    URLSearchParams,
    fetch: (url, init) => {
      fetches.push({ url, body: init && init.body ? String(init.body) : "" });
      return fetchImpl
        ? fetchImpl(url, init)
        : Promise.resolve({ status: 200, json: () => Promise.resolve({ ok: true }) });
    },
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(SOURCE, sandbox);
  const stop = () => {
    timers.forEach((t) => clearInterval(t));
    timers.clear();
  };
  loaded.push(stop);
  return { api: window.inride, overlays, trips, fetches, window, storage: sandbox.localStorage, stop };
}

// The /ride reply for an uploaded ride: the server prefixes the client uuid with its source.
function okUpload() {
  return (url, init) => {
    const dTag = new URLSearchParams(String(init.body)).get("client_d_tag");
    return Promise.resolve({ status: 200, json: () => Promise.resolve({ ok: true, d_tag: "hitchmap-" + dTag }) });
  };
}

const PICKUP = { lat: 51.0817, lon: 13.73629 };
const DROPOFF = { lat: 52.51739, lon: 13.39513 };

// Drive one Finish through the real capture path so the outbox item, the journey-log
// entry and the share-card facts all come from the code under test.
function logFinish(api, pickup, dest) {
  api.journeyStore.set({
    state: "in-ride",
    pickup: pickup,
    coHitchhikers: [],
    waitAccumMs: 0,
    waitSegmentStartMs: null,
    gotRideMs: Date.now() - 90 * 60000,
    finalWaitMs: 12 * 60000,
    wouldRideAgain: true,
    details: { rating: 4 },
    legIndex: 0,
  });
  const j = api.journeyStore.get();
  const id = "ride-" + (api.journeyLogStore.get().length + 1);
  const body = RideSubmit.buildFinishBody(j, dest, Date.now(), id);
  api.outboxStore.add({ id, kind: "finish", createdAt: Date.now(), attempts: 0, lastError: null, status: "pending", body });
  api.journeyLogStore.add({ id, dTag: null, ride: api.rideFactsFromBody(body), at: Date.now() });
  return id;
}

// ── Success overlay ───────────────────────────────────────────────────────────

test("ending a journey opens the success overlay for the LAST ride logged", () => {
  const { api, overlays } = loadInride({ online: false, loggedIn: true });
  logFinish(api, PICKUP, { lat: 51.5, lon: 13.4 });
  logFinish(api, { lat: 51.5, lon: 13.4 }, DROPOFF);

  api.journeyFlow.end();

  assert.strictEqual(overlays.length, 1);
  // The second leg's destination, not the first — a multi-ride journey is confirmed by
  // where it actually got to.
  assert.strictEqual(Number(overlays[0].opts.ride.destLat), DROPOFF.lat);
  assert.strictEqual(Number(overlays[0].opts.ride.pickupLat), 51.5);
});

test("a logged-in journey skips the anonymous sign-up nudge", () => {
  const { api, overlays } = loadInride({ online: false, loggedIn: true });
  logFinish(api, PICKUP, DROPOFF);
  api.journeyFlow.end();
  assert.strictEqual(overlays[0].kind, "");
});

test("an anonymous journey routes through the same sign-up nudge a past ride gets", () => {
  const { api, overlays } = loadInride({ online: false, loggedIn: false });
  logFinish(api, PICKUP, DROPOFF);
  api.journeyFlow.end();
  assert.strictEqual(overlays[0].kind, "anon");
});

test("the overlay opens at once and its ride link resolves when the upload lands", async () => {
  // Give Up finalises the journey in the same breath as queueing the ride, so the d tag
  // is not known yet. The overlay must not wait for it — the share card resolves it.
  const { api, overlays, stop } = loadInride({ online: true, loggedIn: true, fetchImpl: okUpload() });
  logFinish(api, PICKUP, DROPOFF);

  api.journeyFlow.end();
  assert.strictEqual(overlays.length, 1, "shown immediately, not after the upload");
  assert.ok(typeof overlays[0].opts.dTag.then === "function", "the d tag is handed over as a promise");

  await api.flushOutbox();
  assert.strictEqual(await overlays[0].opts.dTag, "hitchmap-ride-1");
  stop();
});

test("an offline journey settles for a share card with no ride link", async () => {
  const { api, overlays } = loadInride({ online: false, loggedIn: true });
  logFinish(api, PICKUP, DROPOFF);
  api.journeyFlow.end();
  // Resolves right away rather than polling for a d tag that cannot arrive.
  assert.strictEqual(await overlays[0].opts.dTag, null);
});

test("ending a journey that logged nothing shows no overlay", () => {
  const { api, overlays } = loadInride({ online: false });
  api.journeyStore.set({ state: "waiting", pickup: PICKUP, waitAccumMs: 0, waitSegmentStartMs: Date.now() });
  api.journeyFlow.end();
  assert.strictEqual(overlays.length, 0);
  assert.strictEqual(api.journeyStore.get(), null);
});

test("discarding a stale journey groups its rides but shows no share card", () => {
  // A card for a ride from another day confirms nothing the user just did.
  const { api, overlays } = loadInride({ online: false });
  logFinish(api, PICKUP, { lat: 51.5, lon: 13.4 });
  logFinish(api, { lat: 51.5, lon: 13.4 }, DROPOFF);
  api.journeyFlow.discard();
  assert.strictEqual(overlays.length, 0);
  assert.ok(api.pendingTripStore.get(), "the trip is still owed");
});

test("the journey log is cleared when the journey ends and when a new one starts", () => {
  const { api } = loadInride({ online: false });
  logFinish(api, PICKUP, DROPOFF);
  api.journeyFlow.end();
  assert.strictEqual(api.journeyLogStore.get().length, 0);

  logFinish(api, PICKUP, DROPOFF);
  api.journeyUI.render = () => {}; // start() draws the dock, which needs a real DOM
  api.journeyFlow.start(PICKUP, []);
  assert.strictEqual(api.journeyLogStore.get().length, 0, "a fresh journey inherits nothing");
});

// ── Auto-grouped trip ─────────────────────────────────────────────────────────

test("a single-ride journey queues no trip", () => {
  const { api, fetches } = loadInride({ online: false });
  logFinish(api, PICKUP, DROPOFF);
  api.journeyFlow.end();
  assert.strictEqual(api.pendingTripStore.get(), null);
  assert.strictEqual(fetches.filter((f) => f.url === "/auto-trip").length, 0);
});

test("a multi-ride journey posts its rides to /auto-trip once they have uploaded", async () => {
  const { api, fetches, trips } = loadInride({ online: true, fetchImpl: okUpload() });
  logFinish(api, PICKUP, { lat: 51.5, lon: 13.4 });
  logFinish(api, { lat: 51.5, lon: 13.4 }, DROPOFF);

  api.journeyFlow.end();
  await api.flushOutbox();
  await new Promise((r) => process.nextTick(r));

  const trip = fetches.find((f) => f.url === "/auto-trip");
  assert.ok(trip, "the grouping POST went out");
  // Server d tags, not the client uuids: the uuid is only the suffix the server prefixes.
  assert.strictEqual(
    new URLSearchParams(trip.body).get("ride_d_tags"),
    "hitchmap-ride-1,hitchmap-ride-2",
  );
  assert.strictEqual(api.pendingTripStore.get(), null, "the record is cleared once grouped");
  assert.strictEqual(trips.length, 1, "the overlay is told about the trip");
});

test("the trip POST waits for a ride still sitting in the outbox", () => {
  const { api, fetches } = loadInride({ online: false });
  logFinish(api, PICKUP, { lat: 51.5, lon: 13.4 });
  logFinish(api, { lat: 51.5, lon: 13.4 }, DROPOFF);
  api.journeyFlow.end();

  // Nothing uploaded yet — grouping rides the server has never seen would just 400.
  assert.strictEqual(fetches.filter((f) => f.url === "/auto-trip").length, 0);
  const rec = api.pendingTripStore.get();
  assert.strictEqual(rec.entries.length, 2);
  assert.ok(rec.entries.every((e) => e.dTag === null));
});

test("legs uploaded before a page reload still make it into the trip", async () => {
  // A long hitch outlives the page: the phone locks and the PWA reloads between legs.
  // The d tags of the legs already uploaded live only in localStorage at that point, so
  // losing them would silently drop those rides from the journey's trip.
  const first = loadInride({ online: true, fetchImpl: okUpload() });
  logFinish(first.api, PICKUP, { lat: 51.5, lon: 13.4 });
  await first.api.flushOutbox();
  assert.strictEqual(first.api.journeyLogStore.get()[0].dTag, "hitchmap-ride-1");

  // Fresh module over the same storage — nothing survives but what was written down.
  const after = loadInride({ online: true, fetchImpl: okUpload(), storage: first.storage });
  logFinish(after.api, { lat: 51.5, lon: 13.4 }, DROPOFF);
  after.api.journeyFlow.end();
  await after.api.flushOutbox();
  await new Promise((r) => process.nextTick(r));

  const trip = after.fetches.find((f) => f.url === "/auto-trip");
  assert.ok(trip, "both legs were groupable");
  assert.strictEqual(
    new URLSearchParams(trip.body).get("ride_d_tags"),
    "hitchmap-ride-1,hitchmap-ride-2",
  );
});

test("a journey finished offline groups itself on a later visit", async () => {
  // The durable half of the feature: the rides sat in the outbox through the whole
  // session, so the grouping has to survive the page being closed and reopened.
  const offline = loadInride({ online: false });
  logFinish(offline.api, PICKUP, { lat: 51.5, lon: 13.4 });
  logFinish(offline.api, { lat: 51.5, lon: 13.4 }, DROPOFF);
  offline.api.journeyFlow.end();
  assert.strictEqual(offline.fetches.filter((f) => f.url === "/auto-trip").length, 0);

  // Same localStorage, fresh module — the phone is back online on a later visit.
  const back = loadInride({ online: true, fetchImpl: okUpload(), storage: offline.storage });
  assert.ok(back.api.pendingTripStore.get(), "the record was read back from storage");
  await back.api.flushOutbox();
  await new Promise((r) => process.nextTick(r));

  const trip = back.fetches.find((f) => f.url === "/auto-trip");
  assert.ok(trip, "the rides uploaded, so the trip finally posts");
  assert.strictEqual(
    new URLSearchParams(trip.body).get("ride_d_tags"),
    "hitchmap-ride-1,hitchmap-ride-2",
  );
  assert.strictEqual(back.api.pendingTripStore.get(), null);
});

test("a trip whose rides never uploaded is dropped after a week", () => {
  const { api, fetches } = loadInride({ online: false });
  api.pendingTripStore.set({
    entries: [{ id: "a", dTag: "hitchmap-a" }, { id: "b", dTag: "hitchmap-b" }],
    createdAt: Date.now() - 8 * 24 * 3600 * 1000,
  });
  api.tryCreateTrip();
  assert.strictEqual(api.pendingTripStore.get(), null);
  assert.strictEqual(fetches.filter((f) => f.url === "/auto-trip").length, 0);
});

test("a rejected ride is dropped from the trip rather than blocking it forever", async () => {
  const { api, fetches } = loadInride({ online: true, fetchImpl: okUpload() });
  api.outboxStore.add({ id: "dead", kind: "finish", createdAt: Date.now(), attempts: 3, lastError: "bad", status: "failed", body: {} });
  api.pendingTripStore.set({
    entries: [
      { id: "dead", dTag: null },
      { id: "a", dTag: "hitchmap-a" },
      { id: "b", dTag: "hitchmap-b" },
    ],
    createdAt: Date.now(),
  });

  api.tryCreateTrip();
  await new Promise((r) => process.nextTick(r));

  const trip = fetches.find((f) => f.url === "/auto-trip");
  assert.strictEqual(new URLSearchParams(trip.body).get("ride_d_tags"), "hitchmap-a,hitchmap-b");
});

test("a 400 from /auto-trip is permanent; a network failure is retried", async () => {
  const refuse = () => Promise.resolve({ status: 400, json: () => Promise.resolve({ ok: false, error: "no" }) });
  const refused = loadInride({ online: true, fetchImpl: refuse });
  const record = { entries: [{ id: "a", dTag: "x" }, { id: "b", dTag: "y" }], createdAt: Date.now() };
  refused.api.pendingTripStore.set(Object.assign({}, record));
  refused.api.tryCreateTrip();
  await new Promise((r) => process.nextTick(r));
  assert.strictEqual(refused.api.pendingTripStore.get(), null, "retrying can only repeat the answer");

  const down = loadInride({ online: true, fetchImpl: () => Promise.reject(new Error("offline")) });
  down.api.pendingTripStore.set(Object.assign({}, record));
  down.api.tryCreateTrip();
  await new Promise((r) => process.nextTick(r));
  assert.ok(down.api.pendingTripStore.get(), "kept for the next attempt");
});

// ── Share-card facts ──────────────────────────────────────────────────────────

test("give-up facts carry no destination and no ride times", () => {
  const { api } = loadInride({ online: false });
  const body = RideSubmit.buildGiveUpBody({ pickup: PICKUP, coHitchhikers: [] }, 45, { rating: 2 }, "g1");
  const facts = api.rideFactsFromBody(body);
  assert.strictEqual(facts.pickupLat, PICKUP.lat);
  assert.strictEqual(facts.destLat, "");
  assert.strictEqual(facts.waitMin, "45");
  assert.strictEqual(facts.departedAt, undefined);
});
