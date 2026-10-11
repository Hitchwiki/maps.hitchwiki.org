// #786: wiki-referred visitors skip the race modal (record-ride always; others 50/50).
// Source-regex test, same style as race_banner_route_link.test.js.
const fs = require("fs");
const assert = require("assert");
const src = fs.readFileSync(__dirname + "/../hitch/static/inride.js", "utf8");
const start = src.indexOf("const raceBanner = {");
const body = src.slice(start, src.indexOf("hmTrack(\"race_banner_shown\"", start)).replace(/\/\/.*$/gm, "");
const g = body.indexOf("const wikiRef");
assert(g > 0, "wiki guard present");
assert(g < body.indexOf("fetch(\"/races.json\")"), "wiki guard runs before the races fetch");
const guardBlock = body.slice(g, body.indexOf("fetch(\"/races.json\")"));
assert(!guardBlock.replace('"hmRaceWikiArmSent"', "").match(/localStorage\.setItem\(raceBanner/), "shown-flag not set by the guard");
assert(guardBlock.includes('"race-wiki-v1", ["skip", "show"]'), "sticky 50/50 arm");
assert(guardBlock.includes("race_wiki_arm"), "arm event fired");
assert(/wiki-record-ride/.test(guardBlock), "record-ride always skips");
const refRe = /^wiki/, rrRe = /^https?:\/\/([a-z0-9-]+\.)*hitchwiki\.org\//i, mapsRe = /^https?:\/\/maps\.hitchwiki\.org\//i;
assert(refRe.test("wiki_main_page") && refRe.test("wiki-safety-de") && !refRe.test("esn_koeln"));
const wr = (u) => rrRe.test(u) && !mapsRe.test(u);
assert(wr("https://hitchwiki.org/en/Berlin") && wr("https://de.hitchwiki.org/x"));
assert(!wr("https://maps.hitchwiki.org/") && !wr("https://example.com/") && !wr(""));
console.log("race_banner_wiki_arm ok");
