// #1669: route() records the reached spot nearest the destination; route_none carries a coarse gap_cell + gap_km (gap-in-middle only).
const fs = require("fs"), assert = require("assert");
const r = fs.readFileSync(__dirname + "/../hitch/static/routing.js", "utf8");
assert(/R\.lastGap = g;/.test(r));
assert(/props\.gap_cell = gp\.lat\.toFixed\(1\)/.test(r) && /props\.gap_km = Math\.round\(gp\.km \/ 10\) \* 10/.test(r));
assert(/reason === "gap-in-middle" && gp/.test(r));
assert(!/gap_cell[^;]*toFixed\([2-9]\)/.test(r), "gap cell must stay at 0.1 deg");
console.log("route_none_gap_cell ok");
