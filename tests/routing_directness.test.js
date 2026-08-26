"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const source = fs.readFileSync(
  path.join(__dirname, "..", "hitch", "static", "routing.js"),
  "utf8"
);

const sandbox = {
  window: {},
  document: { querySelector: () => null },
  fetch: () => new Promise(() => {}),
  setTimeout: () => 0,
};
sandbox.window.window = sandbox.window;
vm.createContext(sandbox);
vm.runInContext(source, sandbox);

const D = sandbox.window.RoutingDirectness;
assert.ok(D, "routing directness helper is exposed");
assert.strictEqual(D.threshold, 2);

const start = [50, 10];
const dest = [50, 11];
const oneDegreeKm = 71.47;

assert.ok(Math.abs(D.routeDistanceRatio(
  { carKm: oneDegreeKm * 1.25, walkKm: 0 }, start, dest
) - 1.25) < 0.01);
assert.strictEqual(D.isCircuitous(
  { carKm: oneDegreeKm * 1.99, walkKm: 0 }, start, dest
), false, "a route below the disclosure threshold stays quiet");
assert.strictEqual(D.isCircuitous(
  { carKm: oneDegreeKm * 2.1, walkKm: 0 }, start, dest
), true, "the issue #116 class of detour is disclosed");
assert.strictEqual(D.routeDistanceRatio(
  { carKm: 0, walkKm: 0 }, start, start
), 1, "coincident endpoints never divide by zero");

const C = sandbox.window.RoutingStartCta;
assert.ok(C, "route-start CTA helper is exposed");
assert.deepStrictEqual(
  Array.from(C.firstBoardingPoint({ legs: [
    { mode: "walk", from: [1, 2], to: [3, 4] },
    { mode: "car", from: [3, 4], to: [5, 6] },
  ] })),
  [3, 4],
  "the CTA starts at the first boarding spot, not the route origin",
);
assert.strictEqual(C.firstBoardingPoint({ legs: [{ mode: "walk" }] }), null);

assert.match(source, /hmVariant\("route-start-cta-v2", \["control", "cta"\]\)/);
assert.match(source, /hmTrack\("route_start_cta_v2_assignment", \{ variant: variant \}\)/);
assert.match(source, /IntersectionObserver/);
assert.match(source, /hmTrack\("route_start_cta_v2_viewed", \{ variant: variant \}\)/);
assert.match(source, /hmTrack\("route_start_cta_v2_clicked", \{ variant: variant \}\)/);
const optionsMarkup = source.slice(
  source.indexOf("body.innerHTML ="),
  source.indexOf('return body.querySelector(".rp-options")'),
);
assert.ok(
  optionsMarkup.indexOf('class="rp-start-cta"') < optionsMarkup.indexOf('class="rp-options"'),
  "the journey CTA must precede the tall route-card list so it is above the fold",
);
assert.match(source, /startFromChoose\([\s\S]*?"route-results"/);
assert.match(source, /hmVariant\("route-none-start-v1", \["control", "cta"\]\)/);
assert.match(source, /hmTrack\("route_none_start_exposure_" \+ variant\)/);
assert.match(source, /hmTrack\("route_none_start_clicked_cta"\)/);
assert.match(source, /class="rp-no-route-cta" hidden/);
assert.match(
  source,
  /const start = RJ\.start\.latlng;[\s\S]*?startFromChoose\([\s\S]*?lat: start\[0\], lon: start\[1\][\s\S]*?"route-results"/,
  "the no-route CTA starts from the searched origin without exposing it to analytics",
);

console.log("routing directness tests passed");
