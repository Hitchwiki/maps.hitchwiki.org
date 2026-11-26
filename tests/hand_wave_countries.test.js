// maps#732: Kazakhstan and Kyrgyzstan show the hand-signal share as a hand wave, not a thumb.
const fs = require("fs");
const assert = require("assert");
const src = fs.readFileSync(__dirname + "/../hitch/static/map.js", "utf8");
assert(src.includes('const HAND_WAVE_COUNTRIES = new Set(["KZ", "KG"]);'));
assert(src.includes('HAND_WAVE_COUNTRIES.has(data.country) ? (v) => tr("🫳 Hand wave {thumb} · Sign {sign} · Ask {ask}"'));
// the thumb button keeps data-method="thumb" so the map filter still works
assert(src.includes('class="spot-country-method" data-method="thumb"'));
console.log("hand_wave_countries ok");
