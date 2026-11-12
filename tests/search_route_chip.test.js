"use strict";
// #1405: search-route-chip-v1 arm; chip only for "on"; events carry arm only; openTo sets dest only.
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const map = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "map.js"), "utf8");
const rt = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "routing.js"), "utf8");
assert.ok(/hmVariant\("search-route-chip-v1", \["off", "on"\]\)/.test(map), "sticky 50/50 arm");
assert.ok(/if \(arm !== "on"\) return;/.test(map), "control sees no chip");
for (const ev of ["search_route_chip_shown", "search_route_chip_clicked"]) {
  const m = map.match(new RegExp('hmTrack\\("' + ev + '"[^;]*;'));
  assert.ok(m && /\{ arm: arm \}/.test(m[0]), ev + " carries the arm only");
}
assert.ok(/RJ\.openTo = openTo;/.test(rt), "openTo exposed");
const fn = rt.match(/function openTo\([\s\S]*?\n  \}/)[0];
assert.ok(/setPoint\("dest"/.test(fn) && !/setPoint\("start"/.test(fn), "openTo sets destination only, no geolocation");
console.log("search_route_chip ok");
