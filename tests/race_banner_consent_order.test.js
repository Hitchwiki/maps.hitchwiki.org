// #654 s3: the race banner waits for the cookie question instead of stacking on it.
const assert = require("assert");
const fs = require("fs");
const src = fs.readFileSync("hitch/static/inride.js", "utf8");
const start = src.indexOf("const raceBanner = {");
const body = src.slice(start, src.indexOf("localStorage.setItem(raceBanner._shownKey(race.title)", start));
assert(/hmVisitorConsent\.state\(\) === "unset"/.test(body), "waits while consent is unset");
assert(/waited >= 30\) return/.test(body), "gives up after 30 s without setting the shown-flag");
assert(/\(ride\|login\|report-ride\)/.test(body), "task paths are not delayed");
console.log("race_banner_consent_order ok");
