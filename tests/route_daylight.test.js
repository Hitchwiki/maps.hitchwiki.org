// IDEAS #1317: the main planner's daylight line uses RGChain with an empty chain; check it stays sane.
const assert = require("assert");
const fs = require("fs");
const C = require("../hitch/static/routing_gang_chain.js");

// Dresden -> Berlin, ~190 km, 120 min drive; leave 08:00 UTC on 2026-11-09 (sunset ~15:30 UTC at 51N).
const leave = Date.UTC(2026, 10, 9, 8, 0);
const s = C.sunset(51.05, 13.74, leave);
assert(!s.polar && s.ms > leave, "sunset after 08:00 UTC");
const avail = (s.ms + 30 * 6e4 - leave) / 6e4;
assert(avail > 300 && avail < 520, "November day length plausible: " + avail);
const r = C.reach(C.timeModel([], 190, 120), avail);
assert(r.likely > 0 && r.possible >= r.likely && r.possible <= 190 + 1);
// Winter, long route: not all the way on a slow day.
const r2 = C.reach(C.timeModel([], 1200, 720), avail);
assert(r2.likely < 1200 - 1);
// map.html must load the chain script before routing.js.
const html = fs.readFileSync(__dirname + "/../hitch/templates/map.html", "utf8");
assert(html.indexOf("routing_gang_chain.js") > 0 && html.indexOf("routing_gang_chain.js") < html.indexOf("/static/routing.js"));
console.log("route_daylight ok", avail.toFixed(0), r.likely.toFixed(0), r2.likely.toFixed(0));
