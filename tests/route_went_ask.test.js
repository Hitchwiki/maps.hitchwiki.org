// #1332: resume chip carries an "I went / Not yet" ask, once per plan.
const fs = require("fs"), assert = require("assert");
const r = fs.readFileSync(__dirname + "/../hitch/static/routing.js", "utf8");
assert(/hmTrack\("route_went", \{ ans: x\[0\]/.test(r));
assert(/getItem\("hmWentAns"\) === String\(rec\.ts\)/.test(r));
console.log("route_went_ask ok");
