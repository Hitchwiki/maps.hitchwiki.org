// #642: a #0,0 hash (wiki page with no coordinates) must not pan to open ocean.
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const SOURCE = fs.readFileSync(path.join(__dirname, "../hitch/static/map.js"), "utf8");

test("navigate() short-circuits 0,0 before panning to raw coordinates", () => {
  const guard = SOURCE.indexOf("if (lat === 0 && lon === 0)");
  const pan = SOURCE.indexOf("map.setView([lat, lon], zoom || 14)");
  assert.ok(guard > 0 && pan > guard, "guard precedes the raw pan");
  assert.match(SOURCE.slice(guard, pan), /showNoLocationNote\(\);\s*return;/);
});

test("arrival is tracked and the note text is translated", () => {
  const fn = SOURCE.match(/function showNoLocationNote\(\) \{[\s\S]*?\n\}\n/)[0];
  assert.match(fn, /hmTrack\("wiki_null_coords_arrival"/);
  assert.match(fn, /tr\("This wiki page has no location yet\./);
});
