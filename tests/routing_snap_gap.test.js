"use strict";

// IDEAS #1708: for an uncovered destination, snap first to the reached spot nearest
// the destination (R.lastGap from the failed search), not to the plain nearest spot,
// which may be an island the start cannot reach.

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const source = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "routing.js"), "utf8");
const sandbox = { window: {}, document: { querySelector: () => null }, fetch: () => new Promise(() => {}), setTimeout: () => 0 };
sandbox.window.window = sandbox.window;
vm.createContext(sandbox);
vm.runInContext(source, sandbox);
const { snapCandidates, buildRouter, ensureWalk, route } = sandbox.window.RoutingInternals;

// 0 -> 1 is a logged corridor; 2 is an island near the destination with no rides to it.
const rep = {
  spots: [[50.0, 10.0], [50.0, 11.0], [50.0, 12.2]],
  trees: [{ s: 0, nodes: [[1, -1, 2, 10]] }],
};
const R = buildRouter(rep); ensureWalk(R);
const from = [50.0, 10.0], dest = [50.0, 12.6]; // dest ~29 km from island 2, ~115 km from spot 1

assert.ok(!route(R, from, dest, 20, null).found, "uncovered destination finds no route");
const c = snapCandidates(R, "dest", from, dest, 150);
assert.strictEqual(c.length, 2, "reached-gap spot and nearest spot are both offered");
assert.deepStrictEqual(Array.from(c[0][0]), [50.0, 11.0], "the reached spot comes first");
assert.ok(route(R, from, c[0][0], 20, null).found, "the reached spot connects");
assert.deepStrictEqual(Array.from(c[1][0]), [50.0, 12.2], "the nearest (island) spot is the fallback");
assert.ok(!route(R, from, c[1][0], 20, null).found, "the island does not connect");

// Start end: no gap shortcut, only the nearest spot.
const s = snapCandidates(R, "start", [50.0, 9.5], [50.0, 11.0], 150);
assert.strictEqual(s.length, 1, "start end only gets the nearest spot");

// Gap beyond the cap is ignored.
R.lastGap = { lat: 50.0, lon: 11.0, km: 400 };
assert.strictEqual(snapCandidates(R, "dest", from, [50.0, 30.0], 150).length, 0, "nothing within the cap");

console.log("routing_snap_gap.test.js OK");
