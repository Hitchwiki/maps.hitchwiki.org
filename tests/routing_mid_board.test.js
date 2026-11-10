"use strict";
// IDEAS #1345: a known spot mid-corridor is boardable (wait x1.5), roots stay unscaled, spotWait ignores mid entries.
const assert = require("assert"), fs = require("fs"), path = require("path"), vm = require("vm");
const sb = { window: {}, document: { querySelector: () => null }, fetch: () => new Promise(() => {}), setTimeout: () => 0 };
sb.window.window = sb.window; vm.createContext(sb);
vm.runInContext(fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "routing.js"), "utf8"), sb);
const { buildRouter, ensureWalk, route } = sb.window.RoutingInternals;
// Corridor A->M->B (M mid, wait 20 on M->B); nothing else reaches B.
const rep = { spots: [[50, 14], [50, 14.5], [50, 15]], trees: [{ s: 0, nodes: [[1, -1, 3, 10], [2, 0, 3, 20]] }] };
const R = buildRouter(rep); ensureWalk(R);
const mid = R.board.get(1);
assert.ok(mid && mid.length === 1 && mid[0][4] === 1.5, "mid node boardable with x1.5 wait factor");
assert.strictEqual(R.board.get(0)[0][4], undefined, "root entry has no factor");
assert.strictEqual(R.spotWait.get(1), undefined, "mid entries do not feed spotWait");
const r = route(R, [50, 14.5], [50, 15], 20, null);
assert.ok(r.found, "rider starting at the mid spot finds the onward ride");
const car = r.legs.find((l) => l.mode === "car");
assert.ok(Math.abs(car.waitMin - 20) < 1e-6, "shown wait is the raw 20 (x1.5 is ranking-only)");
console.log("ok");
