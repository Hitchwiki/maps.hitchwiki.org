// #1336: success overlay offers the planner for a just-saved >=20 km ride; route_judged carries ref.
const fs = require("fs"), assert = require("assert");
const m = fs.readFileSync(__dirname + "/../hitch/static/map.js", "utf8");
const r = fs.readFileSync(__dirname + "/../hitch/static/routing.js", "utf8");
assert(/renderSuccessPlanLink\(successRide\);/.test(m));
assert(/\?ref=ride_saved_plan/.test(m) && /if \(km < 20\) return;/.test(m));
assert(!/tr\("See what the route planner/.test(m));
assert(/route_judged"[^\n]*ref: \(window\.hmLandingRef/.test(r));
console.log("success_plan_link ok");
