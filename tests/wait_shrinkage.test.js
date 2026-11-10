"use strict";
// IDEAS #1348: edge waits are shrunk toward the global median by support.
const assert = require("assert"), fs = require("fs"), path = require("path"), vm = require("vm");
const sb = { window: {}, document: { querySelector: () => null }, fetch: () => new Promise(() => {}), setTimeout: () => 0 };
sb.window.window = sb.window; vm.createContext(sb);
vm.runInContext(fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "routing.js"), "utf8"), sb);
const { buildRouter } = sb.window.RoutingInternals;
// spots 0,1,2; tree A root 0 -> 2 (2 rides, 5 min); tree B root 1 -> 2 (20 rides, 15 min); filler waits set median 20
const spots = [[50, 8], [50.1, 8], [50.5, 8], [50.6, 8]];
const trees = [
  { s: 0, nodes: [[2, -1, 2, 5]] },
  { s: 1, nodes: [[2, -1, 20, 15]] },
  { s: 3, nodes: [[2, -1, 5, 20], [1, 0, 5, 20], [0, 1, 5, 20]] },
];
const R = buildRouter({ spots, trees });
const wA = R.board.get(0)[0][3], wB = R.board.get(1)[0][3];
assert.ok(wA > 5, "2-ride wait pulled toward median: " + wA);
assert.ok(wA > wB, "2-ride 5 min must now rank worse than 20-ride 15 min: " + wA + " vs " + wB);
console.log("ok");
