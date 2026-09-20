// IDEAS #519 slice 1: the race banner carries an A/B arm with a one-tap driver pledge.
// Source-regex test, same style as race_banner_route_link.test.js.
const fs = require("fs");
const assert = require("assert");
const src = fs.readFileSync(__dirname + "/../hitch/static/inride.js", "utf8");
const start = src.indexOf("const raceBanner = {");
const body = src.slice(start, src.indexOf("// ── thinCoverageBanner", start));
assert(/"race-banner-pledge-v1", \["control", "pledge"\]/.test(body), "variant registered");
// Same key map.js writes, so a pledge from either surface silences both.
const mapSrc = fs.readFileSync(__dirname + "/../hitch/static/map.js", "utf8");
assert(mapSrc.includes('const DRIVER_PLEDGE_MADE_KEY = "hmDriverPledgeMade"'));
assert(body.includes('localStorage.getItem("hmDriverPledgeMade")'), "reads the shared key");
assert(body.includes('localStorage.setItem("hmDriverPledgeMade", "1")'), "click writes the shared key");
// A returning pledger is tagged, never assigned to an arm.
assert(body.includes('"already-pledged"'));
// Denominator fires only in the pledge arm, with the surface tag.
assert(/if \(withPledge\) hmTrack\("driver_pledge_shown", \{ surface: "race_banner" \}\)/.test(body));
assert(body.includes('hmTrack("driver_pledge_clicked", { surface: "race_banner" })'));
// Existing banner events carry the variant so the leaderboard-click guardrail is readable.
assert(body.includes('hmTrack("race_banner_shown", { race: race.name, variant: variant })'));
assert(body.includes('hmTrack("race_banner_leaderboard_clicked", { race: race.name, variant: variant })'));
// The success overlay's own pledge events are now separable from the banner's.
assert(mapSrc.includes('hmTrack("driver_pledge_shown", { surface: "success_overlay" })'));
assert(mapSrc.includes('hmTrack("driver_pledge_clicked", { surface: "success_overlay" })'));
assert(!/hmTrack\("driver_pledge_(shown|clicked)", \{\}\)/.test(mapSrc), "no untagged pledge events left");
console.log("race_banner_pledge ok");
