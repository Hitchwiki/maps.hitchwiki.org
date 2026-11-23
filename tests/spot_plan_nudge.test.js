"use strict";
// Till 2026-11-23: after 3 distinct spots within 25 km in one session, the spot sheet offers the planner from here.
const assert = require("assert"), fs = require("fs"), path = require("path");
const map = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "map.js"), "utf8");
const routing = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "routing.js"), "utf8");
assert.ok(map.includes("  renderSpotSummary(data);\n  maybeShowSpotPlanNudge(marker, data);"), "nudge runs on every spot open");
assert.ok(map.includes('hmVariant("spot-plan-nudge-v1", ["control", "show"])'));
assert.ok(map.includes('hmTrack("spot_plan_nudge_eligible", { arm: arm })'));
assert.ok(map.includes("window.RoutingUI.openFrom([from.lat, from.lng], label || null)"));
assert.ok(routing.includes("RJ.openFrom = openFrom;"));
assert.ok(routing.includes('RJ._nextSrc = "spot_nudge";'));

// The distance helper and threshold logic, evaluated standalone.
const km = map.match(/function spotNudgeKm\(a, b\) \{[\s\S]*?\n\}/)[0];
const spotNudgeKm = new Function(km + "; return spotNudgeKm;")();
const berlin = { lat: 52.52, lon: 13.405 }, potsdam = { lat: 52.39, lon: 13.065 }, leipzig = { lat: 51.34, lon: 12.37 };
assert.ok(Math.abs(spotNudgeKm(berlin, potsdam) - 27) < 2, "Berlin-Potsdam ~27 km");
assert.ok(spotNudgeKm(berlin, leipzig) > 140);
assert.strictEqual(spotNudgeKm(berlin, berlin), 0);
console.log("ok");
