const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const source = fs.readFileSync(
  path.join(__dirname, "..", "hitch", "static", "routing.js"), "utf8"
);

test("route sheet asks one yes/no 'would you hitchhike this way' question", () => {
  assert.match(source, /data-judge="yes"/);
  assert.match(source, /data-judge="no"/);
  assert.match(source, /Would you hitchhike this way\?/);
});

test("judgement logs the first answer only, with coarse 0.5 degree cells", () => {
  assert.match(source, /hmTrack\("route_judge_shown"\)/);
  assert.match(source, /hmTrack\("route_judged", \{ answer: button\.dataset\.judge/);
  assert.match(source, /if \(judge\.dataset\.answered\) return/);
  assert.match(source, /Math\.round\(ll\[0\] \* 2\) \/ 2/);
});
