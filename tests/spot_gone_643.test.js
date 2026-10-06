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
  assert.match(MAP, /return `\$\{goneWarning\}\$\{policeNote\}<div>\$\{tr\("Rating:/);
});

test("show.py emits `gone` only for recent reports", () => {
  assert.match(SHOW, /GONE_MIN_YEAR = 2023/);
  assert.match(SHOW, /spot_data\["gone"\] = int\(place\["gone_year"\]\)/);
});

test("#646 police note: newest-report flag, neutral label, tracked", () => {
  assert.match(SHOW, /POLICE_MIN_YEAR = 2024/);
  assert.match(SHOW, /spot_data\["police"\] = int\(place\["police_year"\]\)/);
  assert.match(MAP, /tr\("Latest report \(\{year\}\) mentions police at this spot"/);
  assert.match(MAP, /hmTrack\("spot_police_note_shown"/);
});

test("saved-spots panel reuses the gone warning string", () => {
  const panel = MAP.slice(MAP.indexOf("function toggleSavedSpotsPanel"));
  assert.match(panel, /_data\.gone/);
  assert.match(panel, /tr\("Latest report \(\{year\}\) says this spot may be gone"/);
});
