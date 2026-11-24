const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");
const SOURCE = fs.readFileSync(path.join(__dirname, "../hitch/static/inride.js"), "utf8");

test("journey_finished carries the plan tag (none when unplanned)", () => {
  const i = SOURCE.indexOf('hmTrack("journey_finished"');
  assert.ok(i > 0);
  const body = SOURCE.slice(i, i + 500);
  assert.match(body, /plan: j\.plan \|\| "none"/);
});
