// #1334: no-route result gets an A/B'd dashed road route + known spots; never breaks routing.
const fs = require("fs"), assert = require("assert");
const r = fs.readFileSync(__dirname + "/../hitch/static/routing.js", "utf8");
assert(/showPlannerCompare\(from, to, true\);\n\s+showNoRouteRoad\(from, to\);/.test(r));
assert(/hmVariant\("route-none-road-v1", \["ctrl", "road"\]\)/.test(r));
assert(/route_none_road_shown/.test(r) && /route_none_road_spot_click/.test(r));
assert(/dashArray: "8 8"/.test(r));
assert(!/tr\("[^"]*road/.test(r));
console.log("no_route_road ok");
