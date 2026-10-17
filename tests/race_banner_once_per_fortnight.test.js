// Source-regex test, same style as race_banner_wiki_arm.test.js.
const fs = require("fs");
const assert = require("assert");
const inr = fs.readFileSync(__dirname + "/../hitch/static/inride.js", "utf8");
assert(inr.includes('localStorage.getItem("hmRaceBannerLastMs")'));
assert(inr.includes('14 * 86400000) return;'));
assert(inr.includes('localStorage.setItem("hmRaceBannerLastMs"'));
// the gate must come before the shown-flag is written, so skipped races stay eligible
assert(inr.indexOf('getItem("hmRaceBannerLastMs")') < inr.indexOf("localStorage.setItem(raceBanner._shownKey(race.title)"));
console.log("ok");
