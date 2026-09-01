const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const SOURCE = fs.readFileSync(
  path.join(__dirname, "..", "hitch", "static", "inride.js"),
  "utf8",
);
const MAP_SOURCE = fs.readFileSync(
  path.join(__dirname, "..", "hitch", "static", "map.js"),
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

test("the start picker records that the card was opened, before any terminal outcome", () => {
  // The opened-then-abandoned cohort is the biggest journey-funnel leak
  // (idea #138/#152); without this it's only the button-tap → outcome gap.
  assert.match(SOURCE, /if \(opts\.trackOpen\) outcome\("opened"\)/);
  const startBlock = SOURCE.slice(
    SOURCE.indexOf("const startLauncher ="),
    SOURCE.indexOf("// ── Entry point from map gestures"),
  );
  assert.match(startBlock, /trackOpen: true,/);
  // Only the start-bar picker opts in — the finish/wait pickers must not.
  const finishStart = SOURCE.indexOf('confirmLabel: T("Confirm Drop-off")');
  assert.ok(
    !SOURCE.slice(finishStart, SOURCE.indexOf("});", finishStart)).includes("trackOpen"),
    "the finish drop-off picker must not opt into trackOpen",
  );
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

test("the start picker explains a failed automatic location fix", () => {
  const startBlock = SOURCE.slice(
    SOURCE.indexOf("const startLauncher ="),
    SOURCE.indexOf("// ── Entry point from map gestures"),
  );
  assert.match(startBlock, /autoLocate: true,\s*[\s\S]*?notifyAutoLocateFailure: true,/);
  assert.match(
    SOURCE,
    /if \(opts\.notifyAutoLocateFailure\) \{[\s\S]*?Couldn't get your location — drag the pin instead\./,
  );
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

test("the finish drop-off and wait-elsewhere pickers are also wired to onOutcome (B358/B368)", () => {
  // pinConfirm's onOutcome hook existed for both of these call sites before this,
  // but nothing passed it -- the "Confirm Drop-off" (autoLocate:true, same GPS
  // shape as the start picker) and "Wait somewhere else" (autoLocate:false)
  // pickers had zero outcome tracking, the exact coverage gap B358 flagged.
  assert.match(
    SOURCE,
    /hmTrack\("journey_finish_picker", Object\.assign\(\{ outcome: outcome \}, details\)\)/,
  );
  assert.match(
    SOURCE,
    /hmTrack\("journey_wait_picker", Object\.assign\(\{ outcome: outcome \}, details\)\)/,
  );
  // Each new onOutcome sits inside its own pinConfirm call, not just anywhere in the
  // file -- check it's paired with that picker's own distinguishing confirmLabel.
  const finishBlockStart = SOURCE.indexOf('confirmLabel: T("Confirm Drop-off")');
  const finishBlockEnd = SOURCE.indexOf("});", finishBlockStart);
  assert.ok(
    SOURCE.slice(finishBlockStart, finishBlockEnd).includes("journey_finish_picker"),
    "onOutcome must be inside the Confirm Drop-off pinConfirm call",
  );
});

test("journey start source survives the login redirect and stays bounded", () => {
  assert.match(SOURCE, /const START_SOURCES = \["start-bar", "spot-sheet", "map-gesture", "route-results"\]/);
  assert.match(SOURCE, /START_SOURCES\.includes\(source\) \? source : "unknown"/);
  assert.match(SOURCE, /JSON\.stringify\(\{ lat: p\.lat, lon: p\.lon, source: source \}\)/);
  assert.match(SOURCE, /source: startSource\(source\)/);
  assert.match(SOURCE, /startFromChoose\(latlng, "start-bar"\)/);
  assert.match(SOURCE, /startFromChoose\(latlng, "map-gesture"\)/);
  assert.match(MAP_SOURCE, /startFromChoose\([\s\S]*?"spot-sheet"/);
});
