const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const SRC = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "inride.js"), "utf8");

test("EXP-1200: only spot-sheet and route-results starts enter the at-spot check", () => {
  assert.match(SRC, /const AT_CHECK_SOURCES = \["spot-sheet", "route-results"\]/);
  assert.match(SRC, /if \(!AT_CHECK_SOURCES\.includes\(source\)\) return go\(""\)/);
  assert.match(SRC, /if \(atCheckArm\(\) !== "ask"\) return go\("ctl"\)/);
});

test("EXP-1200: the check never prompts for location and starts silently within 1 km", () => {
  const block = SRC.slice(SRC.indexOf("function atSpotCheck"), SRC.indexOf("journeyFlow.startFromChoose = "));
  assert.match(block, /st\.state !== "granted"\) return once\(ask\)/);
  assert.match(block, /startDistBucket\(p\) === "lt1"/);
  assert.match(block, /go\("skipped_near"\)/);
  assert.match(block, /journey_at_check_not_yet/);
});

test("EXP-1200: journey_started carries at_check and it is one-shot", () => {
  assert.match(SRC, /at_check: atCheckLabel,/);
  assert.match(SRC, /atCheckLabel = ""; \/\/ one-shot/);
});
