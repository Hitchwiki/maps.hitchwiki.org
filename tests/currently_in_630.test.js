// #630: after logging a ride, a signed-in rider can tap "I'm in <city> now".
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const SOURCE = fs.readFileSync(path.join(__dirname, "../hitch/static/map.js"), "utf8");

function loadNearest() {
  const m = SOURCE.match(/const CURRENT_CITY_MAX_KM[\s\S]*?\nfunction wireCurrentCityButton/);
  assert.ok(m, "block found");
  const body = m[0].replace(/\nfunction wireCurrentCityButton$/, "");
  return new Function(body + "; return nearestBigCity;")();
}

test("picks the largest big city within range, not the closest suburb", () => {
  const nearest = loadNearest();
  const cities = [
    { city: "Břevnov", lat: 50.0844, lon: 14.3631, population: 25756 },
    { city: "Prague", lat: 50.0875, lon: 14.4214, population: 1384732 },
    { city: "Kladno", lat: 50.147, lon: 14.103, population: 70000 },
  ];
  assert.strictEqual(nearest(cities, 50.0844, 14.3631).city.city, "Prague");
});

test("offers nothing when no 100k+ city is within 25 km", () => {
  const nearest = loadNearest();
  assert.strictEqual(nearest([{ city: "Prague", lat: 50.0875, lon: 14.4214, population: 1384732 }], 49.0, 14.4), null);
});

test("overlay wiring is signed-in only and tracks offer and set", () => {
  assert.match(SOURCE, /if \(!window\.IS_LOGGED_IN \|\| !isFinite\(lat\)/);
  assert.match(SOURCE, /hmTrack\("currently_in_offered"/);
  assert.match(SOURCE, /hmTrack\("currently_in_set"/);
  assert.match(SOURCE, /wireCurrentCityButton\(ride\);/);
});
