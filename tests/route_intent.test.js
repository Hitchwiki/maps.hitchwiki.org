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

test("intent measures one first choice without retaining a plan", () => {
  assert.match(source, /hmTrack\("route_intent_prompt_shown"\)/);
  assert.match(source, /hmTrack\("route_intent_selected", \{ intent: button\.dataset\.intent \}\)/);
  assert.match(source, /if \(intent\.dataset\.answered\) return/);
  assert.doesNotMatch(source, /localStorage.*route_intent/);
});
