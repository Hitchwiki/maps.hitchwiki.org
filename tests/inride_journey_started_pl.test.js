const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const src = fs.readFileSync(__dirname + "/../hitch/static/inride.js", "utf8");
test("journey_started carries pin placement, set on confirm and cleared after", () => {
  assert.match(src, /pendingPinPlacement = placement;/);
  assert.match(src, /pl: pendingPinPlacement \|\| "none",/);
  assert.match(src, /pendingPinPlacement = "";\n\s*atCheckLabel = "";/);
});
