const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const mapSource = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "map.js"), "utf8");
const start = mapSource.indexOf("const SHARE_DEFERRED_KEY");
const end = mapSource.indexOf("function showSuccessOverlay", start);
const helperSource = mapSource.slice(start, end);

function load(stored, now = 1e12) {
  const events = [];
  const store = new Map(stored ? [["hmShareDeferred", stored]] : []);
  const sandbox = {
    localStorage: {
      getItem: (k) => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => store.set(k, v),
      removeItem: (k) => store.delete(k),
    },
    hmTrack: (name, props) => events.push({ name, props }),
    Date: { now: () => now },
    Number,
    Math,
    JSON,
  };
  vm.createContext(sandbox);
  vm.runInContext(
    helperSource + "; this.note = noteShareDeferred; this.ret = trackShareDeferredReturn",
    sandbox
  );
  return { sandbox, events, store };
}

test("a deferral is stored with a timestamp", () => {
  const { sandbox, store } = load(null);
  sandbox.note();
  assert.strictEqual(store.get("hmShareDeferred"), JSON.stringify({ ts: 1e12 }));
});

test("a return inside 30 days fires once, with whole days, and consumes the key", () => {
  const { sandbox, events, store } = load(JSON.stringify({ ts: 1e12 - 3.5 * 86400000 }));
  sandbox.ret();
  sandbox.ret();
  assert.strictEqual(
    JSON.stringify(events),
    JSON.stringify([{ name: "ride_share_deferred_return", props: { days: 3 } }])
  );
  assert.strictEqual(store.has("hmShareDeferred"), false);
});

test("a stale, future or corrupt deferral fires nothing", () => {
  for (const raw of [
    JSON.stringify({ ts: 1e12 - 31 * 86400000 }),
    JSON.stringify({ ts: 1e12 + 5000 }),
    "not json",
    JSON.stringify({}),
  ]) {
    const { sandbox, events } = load(raw);
    sandbox.ret();
    assert.strictEqual(events.length, 0, raw);
  }
});

test("no deferral, no event", () => {
  const { sandbox, events } = load(null);
  sandbox.ret();
  assert.strictEqual(events.length, 0);
});

test("map.js wires the write to Not now only and the read after the exposure event", () => {
  assert.match(mapSource, /!shareCompleted && via === "not-now"\) noteShareDeferred\(\)/);
  assert.match(
    mapSource,
    /hmTrack\("ride_share_exposure"[^\n]*\n\s*trackShareDeferredReturn\(\);/
  );
});
