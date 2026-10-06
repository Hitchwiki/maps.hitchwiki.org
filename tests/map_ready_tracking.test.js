// #622: map_ready fires once spots are on the map, bucketed by load time.
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const SOURCE = fs.readFileSync(path.join(__dirname, "../hitch/static/map.js"), "utf8");

test("loadMarkers reports map_ready after syncSpotLayer", () => {
  assert.match(SOURCE, /syncSpotLayer\(\);\s*reportMapReady\(url\);/);
});

test("map_ready carries bucket, conn, cached and mobile", () => {
  assert.match(SOURCE, /hmTrack\("map_ready", \{ bucket, conn, cached: String\(cached\), mobile:/);
  for (const b of ['"<2"', '"2-5"', '"5-10"', '"10-20"', '"20-40"', '"40+"'])
    assert.ok(SOURCE.includes(b), b);
});

test("map_boot fires at script start so abandoned loads can be counted", () => {
  const src = require("node:fs").readFileSync(require("node:path").join(__dirname, "../hitch/static/map.js"), "utf8");
  assert.match(src, /hmTrack\("map_boot", \{ mobile:/);
});
