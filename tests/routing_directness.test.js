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

assert.match(source, /hmVariant\("route-start-cta-v1", \["control", "cta"\]\)/);
assert.match(source, /hmTrack\("route_start_cta_exposure", \{ variant: variant \}\)/);
assert.match(source, /hmTrack\("route_start_cta_clicked", \{ variant: variant \}\)/);

console.log("routing directness tests passed");
