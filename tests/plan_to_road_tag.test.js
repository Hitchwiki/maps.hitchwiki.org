// EXP-1331: journeys are tagged with plan recency and a distance bucket to the planned stops.
const fs = require("fs"), assert = require("assert");
const s = fs.readFileSync(__dirname + "/../hitch/static/inride.js", "utf8");
const r = fs.readFileSync(__dirname + "/../hitch/static/routing.js", "utf8");
assert(/plan: j && j\.plan \? j\.plan : "none"/.test(s));
assert(/saveRouteSpots\(\(entry \? \[entry\] : \[\]\)\.concat\(keep\)\)/.test(r));
const src = s.slice(s.indexOf("function planToRoadTag"), s.indexOf("journeyFlow.start = function"));
let store = {};
global.localStorage = { getItem: (k) => (k in store ? store[k] : null) };
const f = new Function("localStorage", src + "; return planToRoadTag;")(global.localStorage);
const P = { lat: 50, lon: 8 };
assert.deepStrictEqual(f(P), { plan: "none", pd: "na" });
store.hmLastRoute = JSON.stringify({ ts: Date.now() - 3600e3, spots: [[50.001, 8.001]] });
assert.deepStrictEqual(f(P), { plan: "s", pd: "lt03" });
store.hmLastRoute = JSON.stringify({ ts: Date.now() - 86400e3, spots: [[50.05, 8]] });
assert.deepStrictEqual(f(P), { plan: "d", pd: "lt20" });
store.hmLastRoute = JSON.stringify({ ts: Date.now() - 20 * 86400e3, spots: [[50, 8]] });
assert.deepStrictEqual(f(P), { plan: "none", pd: "na" });
console.log("plan_to_road_tag ok");
