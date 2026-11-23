"use strict";
// EXP-1347: feedback ask position arm + seen event stay wired.
const assert = require("assert"), fs = require("fs"), path = require("path");
const js = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "routing.js"), "utf8");
assert.ok(js.includes('hmVariant("route-fb-pos-v1", ["control", "top"])'));
assert.ok(js.includes('hmTrack("route_feedback_seen", { arm: fbArm, lang: document.documentElement.lang || "" })'));
assert.ok(js.includes('hmTrack("route_feedback", { vote: vote, arm: fbArm, lang: document.documentElement.lang || "" })'));
assert.ok(/fbArm === "top" && intentEl\) intentEl\.insertAdjacentElement\("beforebegin", box\)/.test(js));
console.log("ok");

assert.ok(js.includes("auto: (navigator.webdriver === true"), "beacon carries the auto flag");

// Till 2026-11-23: styled card shared by both asks; presentation ask at the bottom, tagged aspect=presentation.
assert.ok(js.includes('buildFeedbackCard("rp-feedback", T("Is this a good hitchhiking route?")'));
assert.ok(js.includes('buildFeedbackCard("rp-feedback-ui", T("Is this route easy to understand?")'));
assert.ok(js.includes('aspect: "presentation"'));
assert.ok(js.includes('hmTrack("route_ui_feedback", { vote: vote, lang: lang })'));
assert.ok(/showRouteDriver\(\);\s*showPresentationFeedback\(\);/.test(js), "presentation ask is rendered last");
console.log("ok presentation");
