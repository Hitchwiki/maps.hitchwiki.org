// IDEAS #1258: the country-contact shares are tappable and filter the map by approach method.
const fs = require("fs");
const assert = require("assert");
const src = fs.readFileSync(__dirname + "/../hitch/static/map.js", "utf8");
for (const m of ["thumb", "sign", "asking"]) {
  assert(src.includes(`class="spot-country-method" data-method="${m}"`), m);
}
const wire = src.slice(src.indexOf("function wireSpotCountryMethod"), src.indexOf("function wireSpotCountryPledge"));
assert(wire.includes('hmTrack("spot_country_contact_tapped", { method })'));
assert(wire.includes('setQueryParameter("method", method)'));
assert(/wireSpotCountryPledge\(\);\n\s*wireSpotCountryMethod\(\);/.test(src), "wired after render");
console.log("spot_country_method_tap ok");
