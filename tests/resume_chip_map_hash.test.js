// The resume chip must not be suppressed by the map's own #map= viewport hash.
const fs = require("fs"), assert = require("assert");
const r = fs.readFileSync(__dirname + "/../hitch/static/routing.js", "utf8");
assert(/location\.hash && !\/\^#map=\/\.test\(location\.hash\)/.test(r));
console.log("resume_chip_map_hash ok");
