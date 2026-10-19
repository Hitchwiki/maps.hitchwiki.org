"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "routing.js"), "utf8");

// The click events must sit inside click handlers, never in highlight()
// (which also runs when results render and would count every search as a pick).
const hl = src.match(/function highlight\(i\)[\s\S]*?\n  }\n/);
assert.ok(hl, "highlight() found");
for (const ev of ["route_option_picked", "route_details_clicked", "route_spot_link_clicked"]) {
  assert.ok(src.includes(`hmTrack("${ev}"`), `${ev} is tracked`);
  assert.ok(!hl[0].includes(ev), `${ev} is not fired from highlight()`);
}
assert.ok(/addEventListener\("click", \(\) => \{\s*hmTrack\("route_option_picked"/.test(src), "pick fires inside the click listener");
assert.ok(!/lat|lng|latlng/i.test(src.match(/hmTrack\("route_option_picked"[^)]*\)/)[0]), "no coordinates in the pick payload");
console.log("routing_click_tracking ok");

// #1050: wrong-stop flag sends coordinates rounded to 2 decimals only.
const fl = src.match(/hmTrack\("route_spot_flagged"[^;]*;/);
assert.ok(fl && /toFixed\(2\)/.test(fl[0]) && !/toFixed\([34]\)/.test(fl[0]), "flag payload is 2 decimals");
console.log("flag ok");
