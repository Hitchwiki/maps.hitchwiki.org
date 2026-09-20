// IDEAS #522 slice 2: the spot sheet's country-contact line carries an A/B one-tap driver pledge.
// Source-regex test, same style as race_banner_pledge.test.js.
const fs = require("fs");
const assert = require("assert");
const src = fs.readFileSync(__dirname + "/../hitch/static/map.js", "utf8");
assert(src.includes('window.hmVariant("spot-country-pledge-v1", ["control", "pledge"])'), "variant registered");
const helper = src.slice(src.indexOf("function spotCountryPledgeVariant"), src.indexOf("function renderSpotSummary"));
assert(helper.includes('localStorage.getItem("hmDriverPledgeMade")') && helper.includes('"already-pledged"'), "prior pledgers are tagged, not assigned");
assert(src.includes('const DRIVER_PLEDGE_MADE_KEY = "hmDriverPledgeMade"'));
// Button only renders in the pledge arm, reusing the existing pledge string.
assert(/spotCountryPledgeVariant\(\) === "pledge" \? `<button[^`]*id="spot-country-pledge-btn"[^`]*I'll stop for a hitchhiker when I'm driving/.test(src));
// Denominator fires only in the pledge arm, alongside the variant-tagged shown event.
assert(src.includes("hmTrack('spot_country_contact_shown', { country: spotCountry, variant: pledgeVariant })"));
assert(src.includes('if (pledgeVariant === "pledge") hmTrack("driver_pledge_shown", { surface: "spot_country_contact" })'));
const wire = src.slice(src.indexOf("function wireSpotCountryPledge"), src.indexOf("// #191 / EXP-428"));
assert(wire.includes('hmTrack("driver_pledge_clicked", { surface: "spot_country_contact" })'));
assert(wire.includes("setItem(DRIVER_PLEDGE_MADE_KEY"), "click writes the shared key");
// Wired after every summary render (filter changes rebuild the sheet).
assert(/renderSpotSummary\(view\);\n\s*wireSpotCountryPledge\(\);/.test(src));
console.log("spot_country_pledge ok");
