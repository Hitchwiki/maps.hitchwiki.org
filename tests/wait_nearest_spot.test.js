// #1338: waiting dock offers "Nearest spot: X km" (sticky arm wait-nearest-v1) when no spot is within 200 m.
const fs = require("fs"), assert = require("assert");
const s = fs.readFileSync(__dirname + "/../hitch/static/inride.js", "utf8");
assert(/journeyUI\._renderNearestSpot\(pickup, best, bestKm\);/.test(s));
assert(/"wait-nearest-v1", \["off", "on"\]/.test(s));
assert(/if \(arm !== "on" \|\| bestKm > 15/.test(s));
assert(/hmTrack\("waiting_nearest_shown", \{ arm: arm, km: band \}\)/.test(s));
assert(/hmTrack\("waiting_nearest_clicked"/.test(s));
assert(!/T\("Nearest spot/.test(s));
console.log("wait_nearest_spot ok");
