// #643: the spot sheet warns when show.py flags the newest report as "spot is gone".
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const MAP = fs.readFileSync(path.join(__dirname, "../hitch/static/map.js"), "utf8");
const SHOW = fs.readFileSync(path.join(__dirname, "../hitch/scripts/show.py"), "utf8");

test("spot sheet renders the warning first and tracks it", () => {
  assert.match(MAP, /Number\.isFinite\(data\.gone\)/);
  assert.match(MAP, /tr\("Latest report \(\{year\}\) says this spot may be gone"/);
  assert.match(MAP, /hmTrack\("spot_gone_warning_shown"/);
  assert.match(MAP, /return `\$\{goneWarning\}<div>\$\{tr\("Rating:/);
});

test("show.py emits `gone` only for recent reports", () => {
  assert.match(SHOW, /GONE_MIN_YEAR = 2023/);
  assert.match(SHOW, /spot_data\["gone"\] = int\(place\["gone_year"\]\)/);
});
