const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const ride = fs.readFileSync(__dirname + "/../hitch/static/inride.js", "utf8");
const map = fs.readFileSync(__dirname + "/../hitch/static/map.js", "utf8");

function load() {
  const fn = map.match(/window\.hmNearestSpotM = function[\s\S]*?\n};\n/)[0];
  const bucket = ride.match(/function startNearBucket[\s\S]*?\n  }\n/)[0];
  const window = {};
  const allMarkers = [{ getLatLng: () => ({ lat: 52.0, lng: 13.0 }) }];
  new Function("window", "allMarkers", fn)(window, allMarkers);
  const startNearBucket = new Function("window", bucket + "return startNearBucket;")(window);
  return { window, allMarkers, startNearBucket };
}

test("buckets by distance to the nearest spot", () => {
  const { startNearBucket } = load();
  assert.equal(startNearBucket({ lat: 52.0005, lon: 13.0 }), "lt150"); // ~55 m
  assert.equal(startNearBucket({ lat: 52.005, lon: 13.0 }), "150to1k"); // ~555 m
  assert.equal(startNearBucket({ lat: 52.05, lon: 13.0 }), "gt1k");
});

test("none while spots are not loaded or no point", () => {
  const { window, allMarkers, startNearBucket } = load();
  allMarkers.length = 0;
  assert.equal(startNearBucket({ lat: 52, lon: 13 }), "none");
  assert.equal(startNearBucket(null), "none");
});

test("journey_started carries near", () => {
  assert.match(ride, /near: startNearBucket\(p\),/);
});
