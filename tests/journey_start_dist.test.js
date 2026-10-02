const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const SRC = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "inride.js"), "utf8");
const FN = SRC.match(/function startDistBucket\(p\) \{[\s\S]*?\n  \}\n/)[0];
const bucket = (device, p) => new Function("window", `${FN}; return startDistBucket(${JSON.stringify(p)});`)({ hmDeviceLatLng: device });

test("startDistBucket buckets distance from the last device fix, unknown without one", () => {
  const here = { lat: 47.37, lon: 8.54 };
  assert.equal(bucket(undefined, here), "unknown");
  assert.equal(bucket(here, here), "lt1");
  assert.equal(bucket(here, { lat: 47.40, lon: 8.54 }), "1to5"); // ~3.3 km
  assert.equal(bucket(here, { lat: 47.50, lon: 8.54 }), "5to50"); // ~14 km
  assert.equal(bucket(here, { lat: 48.85, lon: 2.35 }), "gt50"); // Paris
});

test("journey_started carries the dist bucket and map.js records the device fix", () => {
  assert.match(SRC, /source: startSource\(source\),\n\s+dist: startDistBucket\(p\),/);
  const MAP = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "map.js"), "utf8");
  assert.match(MAP, /window\.hmDeviceLatLng = \{ lat: e\.latlng\.lat, lon: e\.latlng\.lng \}/);
});

test("journey_started also carries the joint source:dist key", () => {
  assert.match(SRC, /source_dist: startSource\(source\) \+ ":" \+ startDistBucket\(p\)/);
});
