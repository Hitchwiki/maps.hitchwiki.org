// #1654: one-tap "did you plan this trip with our route planner?" after a ride is saved.
const fs = require("fs"), assert = require("assert");
const m = fs.readFileSync(__dirname + "/../hitch/static/map.js", "utf8");
assert(/renderSuccessPlannerQuestion\(successRide\);/.test(m));
assert(/hmTrack\("ride_planner_used", \{ ans: a\[0\] \}\)/.test(m));
assert(/7 \* 86400000/.test(m) && /hm_ride_planner_q_at/.test(m));
assert(/\["yes", "Yes"\], \["no", "No"\], \["unaware"/.test(m));
assert(/ref=ride_saved_planner_q/.test(m));
console.log("ride_planner_question ok");
