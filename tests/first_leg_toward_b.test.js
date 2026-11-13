// #1426: alternatives() re-ranks by first-leg retreat from B; never drops routes.
const fs = require("fs"), assert = require("assert");
const r = fs.readFileSync(__dirname + "/../hitch/static/routing.js", "utf8");
assert(/const FIRST_LEG_AWAY_MIN = \d+;/.test(r));
assert(/cost\(x\[0\]\) - cost\(y\[0\]\) \|\| x\[1\] - y\[1\]/.test(r));
console.log("first_leg_toward_b ok");
