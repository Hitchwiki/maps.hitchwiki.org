const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");
const SRC = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "inride.js"), "utf8");

test("safety ping row (#305 s1) is control-arm only, tagged, and stores nothing", () => {
  assert.match(SRC, /if \(shareArm === "control" && j\.pickup\) \{\s+const pingRow/);
  assert.match(SRC, /"share-safety-ping"/);
  assert.match(SRC, /hmTrack\("safety_ping_shown"/);
  assert.match(SRC, /hmTrack\("safety_ping_tapped"/);
  assert.match(SRC, /Tell someone you're on your way/);
});
