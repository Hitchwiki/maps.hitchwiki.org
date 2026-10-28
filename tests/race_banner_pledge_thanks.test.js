// IDEAS #1183: the race-banner pledge tap shows a thank-you with the bench-index link.
const fs = require("fs"), assert = require("assert");
const s = fs.readFileSync(__dirname + "/../hitch/static/inride.js", "utf8");
assert(s.includes('"/mitfahrbank?ref=pledge_race_banner"'));
assert(s.includes('hmTrack("driver_pledge_stops_link_clicked", { surface: "race_banner" })'));
console.log("race_banner_pledge_thanks ok");
