// Routing-gang chain: the departure spot is the best-scoring spot within 15 km of A, preferring
// spots whose logged rides went toward B; later hops come from 30-60 km windows.
const assert = require("assert");
const C = require("../hitch/static/routing_gang_chain.js");

const A = [50.0, 10.0], B = [50.0, 12.0]; // B is ~143 km due east of A
const spot = (lat, lon, extra) => Object.assign({ lat, lon, rating: 3, review_count: 1, dest_lats: [], dest_lons: [] }, extra);
const west = spot(50.0, 9.95, { dest_lats: [50.0], dest_lons: [8.0] });      // rides went away from B
const east = spot(50.0, 10.05, { dest_lats: [50.0], dest_lons: [11.0] });    // rides went toward B
assert.strictEqual(C.toward(west, B).ok, 0);
assert.strictEqual(C.toward(east, B).ok, 1);
assert.strictEqual(C.toward(spot(50, 10, {}), B).share, null);

const raw = [A, B];
const [line, cum] = C.densify(raw);
const near = C.nearRoute([west, east, spot(50.0, 10.7), spot(50.0, 11.4)], line, cum, 3);
const chain = C.newChain(A, B, near, cum[cum.length - 1]);
assert.strictEqual(chain[0].s, east, "departure spot prefers rides toward B, even close to A");
assert(chain.length >= 2 && chain.every((c, i) => i === 0 || c.at > chain[i - 1].at), "ordered along the route");
// old behaviour never offered a spot within 10 km of A
assert(C.oldChain(A, B, near).every((c) => C.km(A, [c.s.lat, c.s.lon]) >= 10));
console.log("ok");
