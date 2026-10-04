// IDEAS #603 slice 2: `?pledge=1` shows the existing driver pledge, surface=newsletter.
// Source-regex test, same style as race_banner_pledge.test.js.
const fs = require("fs");
const assert = require("assert");
const src = fs.readFileSync(__dirname + "/../hitch/static/map.js", "utf8");
const start = src.indexOf("function maybeShowNewsletterPledge()");
const body = src.slice(start, src.indexOf("function wireSpotCountryPledge()", start));
assert(start > 0, "function present");
assert(body.includes('get("pledge") === "1"'), "keyed on ?pledge=1");
assert(body.includes("localStorage.getItem(DRIVER_PLEDGE_MADE_KEY)"), "silent for existing pledgers");
assert(body.includes('hmTrack("driver_pledge_shown", { surface: "newsletter" })'));
assert(body.includes('hmTrack("driver_pledge_clicked", { surface: "newsletter" })'));
assert(body.includes("I'll stop for a hitchhiker when I'm driving"), "reuses the existing string");
assert(src.includes("maybeShowNewsletterPledge);"), "invoked at load");
console.log("newsletter_pledge ok");
