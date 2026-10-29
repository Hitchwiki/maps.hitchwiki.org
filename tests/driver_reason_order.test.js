const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const SRC = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "inride.js"), "utf8");

test("EXP-1201b: driver-reason options can be shuffled and the answer logs arm and position", () => {
  assert.match(SRC, /"driver-reason-order-v1", \["fixed", "shuffled"\]/);
  assert.match(SRC, /if \(reasonOrderArm === "shuffled"\)/);
  assert.match(SRC, /hmTrack\("driver_reason_answered", \{\s*reason: driverReason,\s*order: reasonOrderArm,\s*pos:/);
});
