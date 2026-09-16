const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const source = fs.readFileSync(
  path.join(__dirname, "..", "hitch", "static", "routing.js"), "utf8"
);

test("route results expose exactly three bounded optional intent choices", () => {
  assert.match(source, /data-intent="today"/);
  assert.match(source, /data-intent="this-week"/);
  assert.match(source, /data-intent="exploring"/);
  assert.match(source, /When do you plan to hitchhike\? \(optional\)/);
});

test("intent measures one first choice", () => {
  assert.match(source, /hmTrack\("route_intent_prompt_shown"\)/);
  assert.match(source, /hmTrack\("route_intent_selected", \{ intent: button\.dataset\.intent \}\)/);
  assert.match(source, /if \(intent\.dataset\.answered\) return/);
});

test("a same-day 'today' answer is retained on-device for the start-bar nudge, others are not", () => {
  assert.match(source, /ROUTE_INTENT_KEY = "hmRouteIntent"/);
  assert.match(source, /function readRouteIntent/);
  assert.match(source, /function writeRouteIntent/);
  assert.match(source, /function dismissRouteIntent/);
  assert.match(source, /window\.hmRouteIntent = \{ read: readRouteIntent, dismiss: dismissRouteIntent \}/);
  assert.match(source, /if \(intent === "today"\)/);
});
