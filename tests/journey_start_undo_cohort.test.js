const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");
const SOURCE = fs.readFileSync(path.join(__dirname, "../hitch/static/inride.js"), "utf8");

test("journey_start_undo carries the cohort tags (first/returning)", () => {
  const i = SOURCE.indexOf('hmTrack("journey_start_undo"');
  assert.ok(i > 0);
  assert.match(SOURCE.slice(i, i + 200), /cohortProps\(cur\)/);
});
