// #1407: multi-ride routes put the first drop-off town on the sign, final destination beneath.
const fs = require("fs"), assert = require("assert");
const s = fs.readFileSync(__dirname + "/../hitch/static/routing.js", "utf8");
assert(/carLegs\.length < 2/.test(s), "single-ride routes keep the final-destination sign");
assert(/openSign\("route", i, town, \{ final: fin, ll: c \}\)/.test(s));
assert(/name: opts\.final \? "next" : "final"/.test(s), "sign_opened carries which name");
assert(/localSignName\(name, opts\.ll\)/.test(s), "local-script lookup uses the town's point");
console.log("ok sign_next_town");
