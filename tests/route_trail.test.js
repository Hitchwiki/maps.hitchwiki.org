const test = require("node:test");
const assert = require("node:assert");
const RT = require("../hitch/static/route_trail.js");

function env(state, store = {}) {
  const calls = { watch: 0, cleared: 0, removed: 0 };
  let cb;
  const line = { addTo() { return line; }, setLatLngs(p) { line.n = p.length; } };
  return {
    calls, fire: (lat, lon, acc = 10) => cb({ coords: { latitude: lat, longitude: lon, accuracy: acc } }),
    L: { polyline: () => line }, map: { removeLayer() { calls.removed++; } },
    geo: { watchPosition(f) { calls.watch++; cb = f; return 7; }, clearWatch() { calls.cleared++; } },
    permissions: { query: () => Promise.resolve({ state }) },
    storage: { getItem: (k) => store[k] || null, setItem: (k, v) => (store[k] = v), removeItem: (k) => delete store[k] },
    store,
  };
}
const tick = () => new Promise((r) => setImmediate(r));

test("never starts watching unless permission already granted", async () => {
  for (const s of ["prompt", "denied"]) {
    const e = env(s); RT.start(e); await tick();
    assert.equal(e.calls.watch, 0);
  }
});
test("records spaced points, skips close and inaccurate ones", async () => {
  const e = env("granted"); const h = RT.start(e); await tick();
  e.fire(50, 8); e.fire(50.00001, 8); e.fire(50.01, 8); e.fire(50.02, 8, 900);
  assert.equal(h.points.length, 2);
  assert.ok(e.store[RT.KEY]);
});
test("stop wipes storage; stop(true) keeps it", async () => {
  const e = env("granted"); const h = RT.start(e); await tick();
  e.fire(50, 8); h.stop(true); assert.ok(e.store[RT.KEY]);
  const e2 = env("granted", e.store); const h2 = RT.start(e2); await tick();
  assert.equal(h2.points.length, 1); h2.stop();
  assert.equal(e2.store[RT.KEY], undefined); assert.equal(e2.calls.cleared, 1);
});
test("point cap holds", () => {
  const pts = [];
  for (let i = 0; i < 2000; i++) RT.addPoint(pts, [40 + i * 0.001, 8]);
  assert.ok(pts.length <= RT.MAX_POINTS);
});
