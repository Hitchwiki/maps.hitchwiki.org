"use strict";
// #1711: a spot_count mismatch (tab loaded before the daily rebuild) refetches a fresh
// pair and builds the fallback from it, instead of losing the fallback for the tab.
const assert = require("assert"), fs = require("fs"), path = require("path"), vm = require("vm");
const source = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "routing.js"), "utf8");
const oldRep = { spots: [[50, 10], [50, 11]], trees: [] };
const newRep = { spots: [[50, 10], [50, 11], [50, 12]], trees: [] };
const newWeak = { spot_count: 3, trees: [{ s: 0, nodes: [[1, -1, 2, 10], [2, 1, 2, 10]] }] };
const calls = [], events = [];
function run(weakFirst, weakReload, done) {
  calls.length = 0; events.length = 0;
  const resp = (o) => Promise.resolve({ ok: true, json: () => Promise.resolve(o) });
  const sb = { document: { querySelector: () => null }, setTimeout: () => 0, console: { error() {}, log() {} },
    fetch: (u, opt) => { calls.push([u, opt && opt.cache]);
      if (u === "/repeatable_routes.json") return resp(opt ? newRep : oldRep);
      return resp(opt ? weakReload : weakFirst); } };
  sb.window = sb; sb.hmTrack = (n, p) => events.push([n, p]);
  vm.createContext(sb); vm.runInContext(source, sb);
  setImmediate(() => sb.RoutingInternals.loadFallbackRouter().then((R) => done(R)));
}
run(newWeak, newWeak, (R) => {
  assert.ok(R, "fallback recovers after a mismatch");
  assert.strictEqual(R.spots.length, 3, "fallback uses the fresh spot array");
  assert.ok(calls.some(([u, c]) => u === "/repeatable_routes.json" && c === "reload"), "repeatable file refetched with cache reload");
  assert.ok(events.some(([n]) => n === "route_fallback_mismatch"), "mismatch counted");
  assert.ok(!events.some(([n]) => n === "route_fallback_failed"), "not counted as a failure");
  run(newWeak, { spot_count: 5, trees: [] }, (R2) => {
    assert.strictEqual(R2, null, "still-mismatched fresh pair is refused");
    assert.ok(events.some(([n, p]) => n === "route_fallback_failed" && p.why === "mismatch"));
    // Same count, different spots_key: indices shifted, so this must refetch too.
    oldRep.spots_key = "aaa"; newRep.spots_key = "bbb"; newRep.spots = [[50, 10], [50, 11]];
    const shifted = { spot_count: 2, spots_key: "bbb", trees: [] };
    run(shifted, shifted, (R3) => {
      assert.ok(R3, "key mismatch recovers via refetch");
      assert.ok(events.some(([n]) => n === "route_fallback_mismatch"), "same-count key mismatch detected");
      // Matching key on first fetch: no refetch.
      oldRep.spots_key = "bbb";
      run(shifted, shifted, () => {
        assert.ok(!events.some(([n]) => n === "route_fallback_mismatch"), "matching key: no refetch");
        console.log("route_fallback_mismatch.test.js OK");
      });
    });
  });
});
