"use strict";
// EXP-1347: feedback ask position arm + seen event stay wired.
const assert = require("assert"), fs = require("fs"), path = require("path");
const js = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "routing.js"), "utf8");
assert.ok(js.includes('hmVariant("route-fb-pos-v1", ["control", "top"])'));
assert.ok(js.includes('hmTrack("route_feedback_seen", { arm: fbArm, lang: document.documentElement.lang || "" })'));
assert.ok(js.includes('hmTrack("route_feedback", { vote: vote, arm: fbArm })'));
assert.ok(/fbArm === "top" && intentEl\) intentEl\.insertAdjacentElement\("beforebegin", box\)/.test(js));
console.log("ok");
