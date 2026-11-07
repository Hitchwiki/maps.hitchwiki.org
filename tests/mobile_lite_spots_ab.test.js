// #1299: mobile lite-spots A/B. coreToSpots must rebuild spots.json rows (minus destinations).
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const SOURCE = fs.readFileSync(path.join(__dirname, "../hitch/static/map.js"), "utf8");
const m = SOURCE.match(/function coreToSpots\(core\) \{[\s\S]*?\n\}\n/);
const coreToSpots = new Function(`${m[0]}; return coreToSpots;`)();

test("coreToSpots rebuilds rows with flags and optional latest_ms", () => {
  const core = {
    n: 2,
    flag_bits: { osm: 1, cp: 2, fuel: 4, wiki: 8, wikimap: 16 },
    lat: [1.5, 2.5], lon: [3.5, 4.5], rating: [5, 3.2], review_count: [1, 7],
    latest_ms: [null, 1700000000000], flags: [0, 1 | 8],
  };
  assert.deepStrictEqual(coreToSpots(core), [
    { lat: 1.5, lon: 3.5, rating: 5, review_count: 1 },
    { lat: 2.5, lon: 4.5, rating: 3.2, review_count: 7, latest_ms: 1700000000000, osm: true, wiki: true },
  ]);
});

test("both events carry the arm, fallback and details fill exist", () => {
  assert.match(SOURCE, /arm: spotsArm \}\);\s*\n\} catch/);
  assert.match(SOURCE, /mobile: mobile \? "yes" : "no", arm: spotsArm/);
  assert.match(SOURCE, /spots\.core\.json failed, using spots\.json/);
  assert.match(SOURCE, /fullSpotsReady = fillSpotDetails\(url\)/);
  assert.match(SOURCE, /if \(distanceFilter\.value && fullSpotsReady\) await fullSpotsReady/);
});

test("arm is mobile-only, sticky and excludes variation maps and mindistance URLs", () => {
  const f = SOURCE.match(/function pickSpotsArm\(\) \{[\s\S]*?\n\}\n/)[0];
  assert.ok(f.includes("max-width: 700px") && f.includes("hm_spots_arm") && f.includes("MAP_VARIATION") && f.includes("mindistance"));
});
