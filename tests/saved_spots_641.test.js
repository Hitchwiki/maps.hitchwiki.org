// #641: save a spot on the device; a chip lists saved spots with a one-tap start.
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const SOURCE = fs.readFileSync(path.join(__dirname, "../hitch/static/map.js"), "utf8");
const INRIDE = fs.readFileSync(path.join(__dirname, "../hitch/static/inride.js"), "utf8");

function loadHelpers(store) {
  const m = SOURCE.match(/const SAVED_SPOTS_KEY[\s\S]*?\nfunction wireSpotSaveButton/);
  assert.ok(m, "block found");
  const body = m[0].replace(/\nfunction wireSpotSaveButton$/, "");
  const localStorage = {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = v; },
  };
  return new Function("localStorage", body + "; return { loadSavedSpots, storeSavedSpots, sameSpot, SAVED_SPOTS_MAX };")(localStorage);
}

test("round-trips coordinates and caps the list at 20", () => {
  const store = {};
  const h = loadHelpers(store);
  h.storeSavedSpots(Array.from({ length: 25 }, (_, i) => ({ lat: 50 + i / 100, lon: 14 })));
  assert.strictEqual(h.loadSavedSpots().length, h.SAVED_SPOTS_MAX);
});

test("ignores corrupt storage and rows without coordinates", () => {
  const store = { hmSavedSpots: "{not json" };
  assert.deepStrictEqual(loadHelpers(store).loadSavedSpots(), []);
  store.hmSavedSpots = JSON.stringify([{ lat: 1, lon: 2 }, { lat: "x" }, null]);
  assert.strictEqual(loadHelpers(store).loadSavedSpots().length, 1);
});

test("same spot means within ~1 m", () => {
  const h = loadHelpers({});
  assert.ok(h.sameSpot({ lat: 50.12345, lon: 14.1 }, { lat: 50.123451, lon: 14.1 }));
  assert.ok(!h.sameSpot({ lat: 50.12345, lon: 14.1 }, { lat: 50.1235, lon: 14.1 }));
});

test("wiring: star on the spot sheet, start via the in-ride flow with its own source", () => {
  assert.match(SOURCE, /wireSpotSaveButton\(data\);/);
  assert.match(SOURCE, /hmTrack\("spot_saved"/);
  assert.match(SOURCE, /hmTrack\("saved_spot_start_clicked"\)/);
  assert.match(SOURCE, /startFromChoose\(L\.latLng\(spot\.lat, spot\.lon\), "saved-spot"\)/);
  assert.match(INRIDE, /START_SOURCES = \[[^\]]*"saved-spot"/);
});
