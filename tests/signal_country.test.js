// maps#732 slice 2: the "thumb" chip in the ride forms reads "Hand wave" when the pickup is in KZ/KG.
const assert = require("assert");
const path = require("path");
const geo = JSON.parse(require("fs").readFileSync(path.join(__dirname, "../hitch/static/countries.geojson"), "utf8"));
const SC = require("../hitch/static/signal_country.js");

const cases = [
  [42.3, 69.6, true],    // Shymkent, KZ
  [42.87, 74.59, true],  // Bishkek, KG
  [43.24, 76.95, true],  // Almaty, KZ
  [50.28, 57.17, true],  // Aktobe, KZ
  [55.75, 37.62, false], // Moscow — outside the box, no fetch at all
  [41.31, 69.24, false], // Tashkent, UZ — inside the box, polygon says no
  [52.52, 13.4, false],  // Berlin
];
let fetches = 0;
const fetchGeo = () => { fetches++; return Promise.resolve(geo); };
(async () => {
  assert.strictEqual(await SC.isHandWaveAt(55.75, 37.62, fetchGeo), false);
  assert.strictEqual(fetches, 0, "pickups outside KZ/KG's box must not download countries.geojson");
  for (const [lat, lon, want] of cases) {
    assert.strictEqual(await SC.isHandWaveAt(lat, lon, fetchGeo), want, `${lat},${lon}`);
  }
  assert.strictEqual(fetches, 1, "geojson is fetched once and cached");
  assert.strictEqual(await SC.isHandWaveAt("x", 1), false);
  console.log("signal_country ok");
})().catch((e) => { console.error(e); process.exit(1); });
