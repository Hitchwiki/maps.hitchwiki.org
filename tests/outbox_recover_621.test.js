// #621 slice 3: same-minute rejects are re-queued once and counted when they land.
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const SOURCE = fs.readFileSync(path.join(__dirname, "../hitch/static/inride.js"), "utf8");

test("recovery runs once, only for the arrival-time error", () => {
  assert.match(SOURCE, /inride\.recovered621/);
  assert.match(SOURCE, /it\.status === "failed" && \/Arrival time must be later\/\.test\(it\.lastError/);
  assert.match(SOURCE, /function initOutbox\(\) \{\s*recoverSameMinuteRejects\(\);/);
});

test("recovered rides fire journey_ride_recovered on upload", () => {
  assert.match(SOURCE, /if \(item\.recovered\) hmTrack\("journey_ride_recovered"/);
});
