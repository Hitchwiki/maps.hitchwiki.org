const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const source = fs.readFileSync(
  path.join(__dirname, "..", "hitch", "static", "inride.js"), "utf8"
);
const css = fs.readFileSync(
  path.join(__dirname, "..", "hitch", "static", "style.css"), "utf8"
);

test("driver answer row: control arm is the default (no row without hmVariant)", () => {
  assert.match(source, /driver-answer-dock-v1", \["control", "ask"\]/);
  assert.match(source, /driverAnswerArm === "ask"/);
  // The fallback variant helper returns v[0] = "control", so a page without
  // hmVariant never renders the row.
  assert.match(source, /window\.hmVariant \|\| function \(_n, v\) \{ return v\[0\]; \}/);
});

test("driver answer row reuses the seven standard reason codes and shipped labels", () => {
  const expected = [
    "was_hitchhiker", "hospitality_norm", "social_exchange", "curiosity",
    "wanted_driver", "elevated_mood", "sympathy",
  ];
  // The dock row's own chip block (scoped by the driverChipsEl context) carries them.
  const rowBlock = source.slice(
    source.indexOf("driver-answer-dock-v1"),
    source.indexOf("dock.appendChild(driverRow)")
  );
  for (const code of expected) assert.match(rowBlock, new RegExp(`code: "${code}"`));
  assert.doesNotMatch(rowBlock, /textarea/);
});

test("driver taps never pool with the hitchhiker-attributed series", () => {
  const rowBlock = source.slice(
    source.indexOf("driver-answer-dock-v1"),
    source.indexOf("dock.appendChild(driverRow)")
  );
  assert.match(rowBlock, /hmTrack\("driver_answer_tapped", \{ reason: opt\.code \}\)/);
  assert.doesNotMatch(rowBlock, /driver_reason_answered/);
  assert.doesNotMatch(rowBlock, /driver_reason_to_pick_up/);
});

test("driver answer exposure fires once per journey, not per dock re-render", () => {
  assert.match(source, /hmTrack\("driver_answer_row_shown", \{ arm: driverAnswerArm \}\)/);
  assert.match(source, /!j\.driverAnswerShown/);
  assert.match(source, /cur\.driverAnswerShown = true/);
});

test("driver answer row is styled as a stacked-dock child (no flex-basis overlap)", () => {
  assert.match(css, /\.inr-dock--stack > \.inr-driver-row/);
  assert.match(css, /\.inr-driver-row \{/);
});
