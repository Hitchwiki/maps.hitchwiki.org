// IDEAS #1257: pledge thank-you second slot is a 50/50 arm: "Spots near you" vs "Why drivers stopped".
const fs = require("fs"), assert = require("assert");
const s = fs.readFileSync(__dirname + "/../hitch/static/inride.js", "utf8");
assert(s.includes('hmPledgeTryArm'));
assert(s.includes('driver_pledge_thanks_shown'));
assert(s.includes('/?ref=pledge_try'));
assert(s.includes('/statistics/driver-reasons?ref=pledge_thanks'), "control link kept");
console.log("pledge_try_arm ok");
