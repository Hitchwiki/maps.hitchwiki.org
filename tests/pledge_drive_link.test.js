// #1333: pledge note links to the planner's driver view; a pledge_drive landing forces its own arm.
const fs = require("fs"), assert = require("assert");
const m = fs.readFileSync(__dirname + "/../hitch/static/map.js", "utf8");
const r = fs.readFileSync(__dirname + "/../hitch/static/routing.js", "utf8");
assert(/"\/\?ref=pledge_drive_" \+ surface/.test(m));
assert(/if \(pledged\) arm = "pledge"/.test(r));
assert(!/localStorage\.setItem\("route-drive-v1", "pledge"/.test(r));
assert(/arm !== "on" && arm !== "pledge"/.test(r));
console.log("pledge_drive_link ok");
