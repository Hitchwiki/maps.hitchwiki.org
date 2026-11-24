const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");
const SOURCE = fs.readFileSync(path.join(__dirname, "../hitch/static/inride.js"), "utf8");

test("journey_next_leg carries lpd only for planned journeys", () => {
  const i = SOURCE.indexOf("journeyFlow.nextRide = function");
  assert.ok(i > 0);
  const body = SOURCE.slice(i, i + 2200);
  assert.match(body, /j\.plan && j\.plan !== "none"/);
  assert.match(body, /lpd = planToRoadTag\(p\)\.pd/);
  assert.match(body, /hmTrack\("journey_next_leg", legProps\)/);
});
