"use strict";
// #1339B: route-nav-v1 arm. Link only for the "on" arm, only once per itinerary, no coordinates in events.
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const src = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "routing.js"), "utf8");
assert.ok(/hmVariant\("route-nav-v1", \["off", "on"\]\)/.test(src), "sticky 50/50 arm");
assert.ok(/RJ\._navDone = false;\s*\n\s*ol\.appendChild\(nodeRow\(t, base, "start"/.test(src), "flag reset per itinerary");
assert.ok(/if \(arm === "on"\)/.test(src), "link gated on the on arm");
for (const ev of ["route_nav_shown", "route_nav_clicked"]) {
  const m = src.match(new RegExp('hmTrack\\("' + ev + '"[^;]*;'));
  assert.ok(m && !/c\[0\]|lat|lon/.test(m[0]), ev + " carries no coordinates");
}
assert.ok(/T\("Go to on Google Maps"\)/.test(src), "reuses the translated key");
console.log("route_nav_arm ok");
