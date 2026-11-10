// #1339A: outbound spot-sheet links are counted (kind only, no spot id).
const fs = require("fs"), assert = require("assert");
const m = fs.readFileSync(__dirname + "/../hitch/static/map.js", "utf8");
assert(/hmTrack\("spot_nav_clicked", \{ kind: pr\[1\], touch:/.test(m));
assert(/\["spot-google-link", "maps"\]/.test(m) && /\["spot-streetview-link", "streetview"\]/.test(m) && /\["spot-osm-link", "osm"\]/.test(m));
assert(!/spot_nav_clicked[^\n]*lat/.test(m));
console.log("spot_nav_click ok");
