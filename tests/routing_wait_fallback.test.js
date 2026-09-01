"use strict";

// Node-level wait fallback (IDEAS.md #70): when a boardable edge logged no wait,
// the router should fall back to the boarding spot's own mean recorded wait
// before the global default. Mirrors tests/test_repeatable_router.py's
// test_node_level_wait_fallback_beats_global_default.

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

const { buildRouter, ensureWalk, route } = sandbox.window.RoutingInternals;
assert.ok(buildRouter && route, "routing internals are exposed for tests");

// A (0) roots two corridors: A->B logged a 12-min wait, A->C logged none.
// A far-away corridor E->F logged 90, so defaultWait = (12 + 90) / 2 = 51.
const rep = {
  spots: [
    [50.0, 14.0], // A
    [50.0, 14.5], // B
    [50.0, 13.5], // C
    [40.0, 0.0], // E
    [40.0, 0.5], // F
  ],
  trees: [
    { s: 0, nodes: [[1, -1, 2, 12]] }, // A->B, wait 12
    { s: 0, nodes: [[2, -1, 2]] }, // A->C, wait unrecorded
    { s: 3, nodes: [[4, -1, 2, 90]] }, // E->F, wait 90
  ],
};

const R = buildRouter(rep); ensureWalk(R);
assert.strictEqual(Math.round(R.defaultWait), 51, "global default wait is 51");
assert.strictEqual(R.spotWait.get(0), 12, "spot A's own mean wait is 12");

const res = route(R, [50.0, 14.0], [50.0, 13.5], 0.5, null); // A -> C
assert.ok(res.found, "a route A->C is found");
assert.strictEqual(
  Math.round(res.waitMin),
  12,
  "boarding A->C falls back to spot A's 12, not the global 51"
);

console.log("routing_wait_fallback.test.js OK");
