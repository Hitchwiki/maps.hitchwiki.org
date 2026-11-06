const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const src = fs.readFileSync(__dirname + "/../hitch/static/inride.js", "utf8");
test("rating-optional arm: assignment, tag, enabled button, guard", () => {
  assert.ok(src.includes('("ride_rating_optional_v1", ["ctrl", "opt"])'));
  assert.ok(src.includes('ro: j && j.ratingOptArm ? j.ratingOptArm : "na"'));
  assert.ok(src.includes("const ready = ratingOptional || rating > 0;"));
  assert.ok(src.includes("if (!rating && !ratingOptional) return;"));
  assert.ok(src.includes("rideOnBtn.disabled = !ratingOptional;"));
});
