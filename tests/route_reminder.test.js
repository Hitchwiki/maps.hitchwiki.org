const fs = require("fs"), assert = require("assert");
const r = fs.readFileSync(__dirname + "/../hitch/static/routing.js", "utf8");
assert(r.includes("function showRouteReminder()"), "reminder fn");
assert(r.includes("showRouteFeedback();\n    showRouteReminder();"), "called after feedback");
assert(r.includes('hmTrack("route_reminder_saved"'), "save event");
assert(r.includes("?ref=trip_reminder"), "ref");
assert(r.includes("/* must never break routing */"), "guarded");
console.log("ok");
