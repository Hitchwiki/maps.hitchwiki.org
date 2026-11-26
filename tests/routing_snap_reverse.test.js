"use strict";

// IDEAS #1708 slice 2: for an uncovered start, snap first to the spot nearest the start
// that can reach the destination (backward search), not to the plain nearest spot,
// which may be an island with no rides toward the destination.

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const source = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "routing.js"), "utf8");
const sandbox = { window: {}, document: { querySelector: () => null }, fetch: () => new Promise(() => {}), setTimeout: () => 0 };
sandbox.window.window = sandbox.window;
vm.createContext(sandbox);
vm.runInContext(source, sandbox);
const { snapCandidates, reverseReach, buildRouter, ensureWalk, route } = sandbox.window.RoutingInternals;

// 0 -> 1 is a logged corridor; 2 is an island nearer the start with no rides from it.
const rep = {
  spots: [[50.0, 10.0], [50.0, 11.0], [50.0, 9.0]],
  trees: [{ s: 0, nodes: [[1, -1, 2, 10]] }],
};
const R = buildRouter(rep); ensureWalk(R);
const start = [50.0, 8.6], dest = [50.0, 11.05]; // start ~29 km from island 2, ~100 km from spot 0

assert.ok(!route(R, start, dest, 20, null).found, "uncovered start finds no route");
const reach = reverseReach(R, dest, 20);
assert.ok(reach.has(0) && reach.has(1) && !reach.has(2), "backward search finds 0 and 1, not the island");
const c = snapCandidates(R, "start", start, dest, 150);
assert.strictEqual(c.length, 2, "reachable spot and nearest spot are both offered");
assert.deepStrictEqual(Array.from(c[0][0]), [50.0, 10.0], "the reachable spot comes first");
assert.strictEqual(c[0][2], "rev");
assert.ok(route(R, c[0][0], dest, 20, null).found, "the reachable spot connects");
assert.deepStrictEqual(Array.from(c[1][0]), [50.0, 9.0], "the nearest (island) spot is the fallback");
assert.strictEqual(c[1][2], "nearest");

// Nothing reachable within the cap: only the plain nearest spot, if any.
assert.strictEqual(snapCandidates(R, "start", [50.0, 2.0], dest, 150).length, 0, "nothing within the cap");

console.log("routing_snap_reverse.test.js OK");
