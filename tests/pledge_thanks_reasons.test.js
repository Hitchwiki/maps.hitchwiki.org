// IDEAS #1185: pledge thank-you also links the existing "Why drivers stopped" stats page.
const fs = require("fs"), assert = require("assert");
const s = fs.readFileSync(__dirname + "/../hitch/static/inride.js", "utf8");
assert(s.includes('/statistics/driver-reasons?ref=pledge_thanks'));
assert(s.includes('driver_pledge_reasons_link_clicked'));
console.log("pledge_thanks_reasons ok");
