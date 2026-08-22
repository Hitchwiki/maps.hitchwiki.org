"use strict";

const assert = require("assert");
const countryGpx = require("../hitch/static/country_gpx.js");

assert.deepStrictEqual(
  countryGpx.entries({
    FR: { name: "France", spot_count: 200 },
    DE: { name: "Germany", spot_count: 300 },
    "../": { name: "unsafe", spot_count: 1 },
  }).map(([code]) => code),
  ["FR", "DE"],
  "country choices are alphabetical and unsafe path components are excluded",
);
assert.strictEqual(countryGpx.href("DE"), "/spots_by_country/DE.gpx");
assert.strictEqual(countryGpx.href("../"), null);
assert.strictEqual(countryGpx.size(52 * 1024), "52 KB");
assert.strictEqual(countryGpx.size(1.24 * 1024 * 1024), "1.2 MB");

console.log("country GPX tests passed");
