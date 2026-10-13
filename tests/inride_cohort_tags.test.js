const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const SOURCE = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "inride.js"), "utf8");

// #820: first-journey / logged-in cohort tags on the journey outcome events, so first-timer
// failure share can be read from Umami without a join.
test("cohortProps tags first/li as yes/no strings plus the bounded source", () => {
  assert.match(SOURCE, /first: j && j\.firstJourney \? "yes" : "no"/);
  assert.match(SOURCE, /li: window\.IS_LOGGED_IN \? "yes" : "no"/);
  assert.match(SOURCE, /source: startSource\(j && j\.source\)/);
});

test("the three outcome events carry the cohort tags", () => {
  for (const ev of ["journey_cancelled", "journey_gave_up", "journey_got_ride"]) {
    const i = SOURCE.indexOf(`hmTrack("${ev}"`);
    assert.ok(i > 0, ev);
    assert.ok(SOURCE.slice(i, i + 400).includes("cohortProps(j)"), `${ev} lacks cohortProps`);
  }
});

test("journey_started carries first and li", () => {
  const i = SOURCE.indexOf('hmTrack("journey_started"');
  const block = SOURCE.slice(i, SOURCE.indexOf("journeyUI.render(j)", i));
  assert.match(block, /first: j\.firstJourney \? "yes" : "no"/);
  assert.match(block, /li: window\.IS_LOGGED_IN \? "yes" : "no"/);
});

test("journey_rehydrated fires only for a non-stale restored journey, with a bounded age bucket", () => {
  const i = SOURCE.indexOf('hmTrack("journey_rehydrated"');
  assert.ok(i > 0);
  const before = SOURCE.slice(i - 200, i);
  assert.match(before, /ageMs <= STALE_MS/);
  assert.match(SOURCE.slice(i, i + 400), /"lt1h"[\s\S]*"1to6h"[\s\S]*"6to24h"/);
});
