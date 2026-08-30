const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const source = fs.readFileSync(
  path.join(__dirname, "..", "hitch", "static", "inride.js"), "utf8"
);

test("pickup sheet offers only bounded standard driver-reason codes", () => {
  const expected = [
    "was_hitchhiker", "social_exchange", "curiosity", "sympathy", "environmental",
  ];
  for (const code of expected) assert.match(source, new RegExp(`code: "${code}"`));
  assert.match(source, /driver_reason_to_pick_up: driverReason \? \[driverReason\] : \[\]/);
  assert.doesNotMatch(source, /driverReason.*textarea/);
});

test("pickup sheet measures exposure and answered reason separately", () => {
  assert.match(source, /hmTrack\("driver_reason_prompt_shown"\)/);
  assert.match(source, /hmTrack\("driver_reason_answered", \{ reason: driverReason \}\)/);
});
