// IDEAS #839: every pledge thank-you carries a link to the bench index, with a click event.
const fs = require("fs"), assert = require("assert");
const map = fs.readFileSync(__dirname + "/../hitch/static/map.js", "utf8");
assert(map.includes("function addPledgeStopsLink(note, surface)"));
assert(map.includes('"driver_pledge_stops_link_clicked"'));
for (const s of ['"success_overlay"', '"spot_country_contact"', "surface"])
  assert(map.includes("addPledgeStopsLink(note, " + s + ");"), s);
console.log("pledge_stops_link ok");
