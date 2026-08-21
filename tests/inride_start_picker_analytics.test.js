const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const SOURCE = fs.readFileSync(
  path.join(__dirname, "..", "hitch", "static", "inride.js"),
  "utf8",
);

test("the start picker sends one aggregate event with an outcome property", () => {
  assert.match(
    SOURCE,
    /hmTrack\("journey_start_picker", Object\.assign\(\{ outcome: outcome \}, details\)\)/,
  );
  assert.match(SOURCE, /outcome\("confirmed", \{ placement: placement \}\);\s*cleanup\(\)/);
  assert.match(SOURCE, /outcome\("cancelled", \{ placement: placement \}\);\s*cleanup\(\)/);
});

test("location outcomes distinguish failure, use, and a late ignored fix", () => {
  for (const outcome of [
    "auto-location-used",
    "auto-location-ignored",
    "auto-location-failed",
    "location-button-used",
    "location-button-failed",
  ]) {
    assert.match(SOURCE, new RegExp(`outcome\\("${outcome}"`));
  }
});

test("confirmed placement records every way the pin can move", () => {
  for (const placement of [
    "map-centre",
    "drag",
    "map-tap",
    "long-press",
    "auto-location",
    "location-button",
  ]) {
    assert.ok(SOURCE.includes(`"${placement}"`), `missing ${placement}`);
  }
});
