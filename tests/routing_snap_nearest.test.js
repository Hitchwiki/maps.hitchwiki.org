"use strict";

// IDEAS #649: when one end of a search is farther than the walk limit from any
// logged spot, the planner retries from the nearest graph spot. This pins the
// pieces that decide whether that button is shown.

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const source = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "routing.js"), "utf8");
const sandbox = { window: {}, document: { querySelector: () => null }, fetch: () => new Promise(() => {}), setTimeout: () => 0 };
sandbox.window.window = sandbox.window;
vm.createContext(sandbox);
vm.runInContext(source, sandbox);
const { nearestSpot, buildRouter, ensureWalk, route } = sandbox.window.RoutingInternals;

const rep = {
  spots: [[50.0, 14.0], [50.0, 14.5], [40.0, 0.0]],
  trees: [{ s: 0, nodes: [[1, -1, 2, 10]] }],
};
const R = buildRouter(rep); ensureWalk(R);

const far = [50.0, 12.0]; // ~143 km west of spot 0, beyond the 20 km walk limit
assert.ok(!route(R, far, [50.0, 14.5], 20, null).found, "uncovered start finds no route");

const near = nearestSpot(R, far, 150);
assert.strictEqual(near[0], 0, "nearest covered spot is A");
assert.ok(near[1] > 100 && near[1] < 150, "distance is reported in km");
assert.ok(route(R, R.spots[near[0]], [50.0, 14.5], 20, null).found, "snapped start connects");

assert.strictEqual(nearestSpot(R, [60.0, 60.0], 150), null, "nothing within the cap means no button");

console.log("routing_snap_nearest.test.js OK");
