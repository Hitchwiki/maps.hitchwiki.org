// IDEAS #531: a week after a driver pledge, ask once (max twice) whether it happened.
const fs = require("fs");
const assert = require("assert");
const inr = fs.readFileSync(__dirname + "/../hitch/static/inride.js", "utf8");
const map = fs.readFileSync(__dirname + "/../hitch/static/map.js", "utf8");
// All three pledge surfaces stamp time + surface.
assert(map.includes('noteDriverPledgeTime("success_overlay")'));
assert(map.includes('noteDriverPledgeTime("spot_country_contact")'));
assert(inr.includes('localStorage.setItem("hmDriverPledgeSurface", "race_banner")'));
assert(inr.includes('localStorage.setItem("hmDriverPledgedAt", String(Date.now()))'));
const start = inr.indexOf("const driverPledgeFollowup = {");
const body = inr.slice(start, inr.indexOf("// ── thinCoverageBanner", start));
assert(body.includes("WAIT_MS: 7 * 86400000") && body.includes("MAX_ASKS: 2"));
// Non-pledgers and answered devices never see it; legacy pledgers are stamped, not asked.
assert(body.includes('if (!localStorage.getItem("hmDriverPledgeMade")) return;'));
assert(body.includes('if (localStorage.getItem("hmDriverFollowupDone")) return;'));
assert(/if \(!\(at > 0\)\) \{ localStorage\.setItem\("hmDriverPledgedAt"[^}]*return; \}/.test(body));
// Never over a journey, an open dialog, or a shared route link.
assert(body.includes("journeyStore.get() || journeyUI._openDialog"));
assert(body.includes("dir"));
// Events.
for (const e of ["driver_pledge_followup_shown", "driver_pledge_followup_answered", "driver_pledge_followup_dismissed"]) assert(body.includes(e), e);
assert(/answer\("yes"\)/.test(body) && /answer\("not_yet"\)/.test(body));
// Wired after the race banner / thin coverage, delayed.
assert(/setTimeout\(driverPledgeFollowup\.check, 6000\)/.test(inr));
console.log("driver_pledge_followup ok");
