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

test("a failed location fix carries the reason it failed, not just 'failed'", () => {
  // The picker's auto-location failure was one unclassified bucket at ~52% of
  // GPS attempts (idea #15 / research/journey-picker-gps-failure-split). denied,
  // timeout, unavailable and no-api have different fixes, so each outcome event
  // now carries { reason }.
  assert.match(
    SOURCE,
    /getFixWithRetry\([^)]*\)\s*\{\s*\n\s*if \(!navigator\.geolocation\) return Promise\.reject\(\{ code: "no-api" \}\)/,
  );
  // TIMEOUT (code 3) is split out from POSITION_UNAVAILABLE (code 2).
  assert.match(SOURCE, /reject\(\{ code: err\.code === 3 \? "timeout" : "unavailable" \}\)/);
  // still terminal on PERMISSION_DENIED
  assert.match(SOURCE, /if \(err\.code === 1\) return reject\(\{ code: "denied" \}\)/);
  // both picker failure handlers forward the reason
  assert.match(
    SOURCE,
    /outcome\("auto-location-failed", \{ reason: \(err && err\.code\) \|\| "unknown" \}\)/,
  );
  assert.match(
    SOURCE,
    /outcome\("location-button-failed", \{ reason: \(err && err\.code\) \|\| "unknown" \}\)/,
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

test("journey source survives in local state through first-ride conversion", () => {
  assert.match(SOURCE, /legIndex: 0,\s*source: startSource\(source\)/);
  assert.match(
    SOURCE,
    /hmTrack\("journey_got_ride", \{[\s\S]*?source: startSource\(j\.source\)/,
  );
});

test("picker outcomes carry the geolocation permission state, declared before the first outcome fires", () => {
  // `let permState` is in the temporal dead zone until its declaration runs, so it must sit
  // above the trackOpen call that reaches outcome() synchronously.
  const decl = SOURCE.indexOf('let permState = "";');
  assert.ok(decl > 0, "permState must be declared");
  assert.ok(
    decl < SOURCE.indexOf('if (opts.trackOpen) outcome("opened")'),
    "permState must be declared before outcome('opened') can read it",
  );
  assert.match(SOURCE, /navigator\.permissions\.query\(\{ name: "geolocation" \}\)/);
  assert.match(SOURCE, /Object\.assign\(\{ perm: permState \}, details\)/);
});
