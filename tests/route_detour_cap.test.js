// #1420: alternatives() must never offer a chain that drives >4x the straight line + 150 km.
const fs = require("fs"), assert = require("assert");
const r = fs.readFileSync(__dirname + "/../hitch/static/routing.js", "utf8");
assert(/res\.carKm > 4 \* haversineKm\(start, dest\) \+ 150\) continue;/.test(r));
// the cap sits inside alternatives(), after the penalty bookkeeping
const a = r.indexOf("function alternatives(");
assert(a > 0 && r.indexOf("res.carKm > 4 *", a) > a);
console.log("route_detour_cap ok");
