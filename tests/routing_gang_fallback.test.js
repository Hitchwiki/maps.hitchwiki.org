const assert = require("assert");
const C = require("../hitch/static/routing_gang_chain.js");
const F = require("../hitch/static/routing_gang_fallback.js");
const A = [50.0, 10.0], B = [50.0, 12.0];
const [line, cum] = C.densify([A, B]);
const els = [
  { lat: 50.0, lon: 10.3, tags: { amenity: "fuel" } },
  { lat: 50.0, lon: 10.1, tags: { amenity: "fuel" } },
  { lat: 50.2, lon: 10.05, tags: { amenity: "fuel" } },          // 22 km off the route
  { center: { lat: 50.0, lon: 10.02 }, tags: { highway: "rest_area" } },
  { lat: 50.0, lon: 10.0, tags: { shop: "bakery" } },            // not a stopping place
];
const f = F.fallback(els, line, cum, 3, C.km);
assert.strictEqual(f.kind, "rest_area");
assert(f.label.includes("(OSM)") && f.label.includes("no rides logged"));
assert.strictEqual(F.fallback([], line, cum, 3, C.km), null);
assert(F.overpassQuery(50, 10, 15000).includes("amenity=fuel"));
console.log("ok");
