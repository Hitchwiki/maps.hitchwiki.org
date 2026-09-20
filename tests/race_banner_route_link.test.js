// A visitor arriving on a shared /dir/ route link must not get the race modal on top
// of the route. Source-regex test, same style as the other inride tests.
const fs = require("fs");
const assert = require("assert");
const src = fs.readFileSync(__dirname + "/../hitch/static/inride.js", "utf8");
const start = src.indexOf("const raceBanner = {");
const body = src.slice(start, src.indexOf("hmTrack(\"race_banner_shown\"", start)).replace(/\/\/.*$/gm, "");
const guard = body.indexOf("dir\\/-?\\d/.test(location.pathname)");
assert(guard > 0, "route-link guard present");
assert(guard < body.indexOf("fetch(\"/races.json\")"), "guard runs before the races fetch");
assert(!body.slice(0, guard).includes("setItem"), "shown-flag is not set before the guard");
// The regex itself: matches route paths (incl. language prefix), not the map root or /races.
const re = /(^|\/)dir\/-?\d/;
assert(re.test("/dir/52.5,13.4/48.1,11.5"));
assert(re.test("/de/dir/52.5,13.4/48.1,11.5"));
assert(!re.test("/") && !re.test("/races") && !re.test("/de"));
console.log("race_banner_route_link ok");
// Legacy #dir/ links (pathname stays "/") are guarded by the same line.
assert(body.includes('location.hash.slice(1).startsWith("dir/")'), "legacy #dir guard present");
