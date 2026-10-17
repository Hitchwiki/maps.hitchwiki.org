// Routing-gang chain: the departure spot is the best-scoring spot within 15 km of A, preferring
// spots whose logged rides went toward B; later hops come from 20-80 km windows.
const assert = require("assert");
const C = require("../hitch/static/routing_gang_chain.js");

const A = [50.0, 10.0], B = [50.0, 12.0]; // B is ~143 km due east of A
const spot = (lat, lon, extra) => Object.assign({ lat, lon, rating: 3, review_count: 1, dest_lats: [], dest_lons: [] }, extra);
const west = spot(50.0, 9.95, { dest_lats: [50.0], dest_lons: [8.0] });      // rides went away from B
const east = spot(50.0, 10.05, { dest_lats: [50.0], dest_lons: [11.0] });    // rides went toward B
assert.strictEqual(C.toward(west, B).ok, 0);
assert.strictEqual(C.toward(east, B).ok, 1);
assert.strictEqual(C.toward(spot(50, 10, {}), B).share, null);
const far = spot(50.0, 10.0, { dest_lats: [50.0, 50.0, 50.0, 50.0], dest_lons: [10.2, 10.5, 11.0, 8.0] });
assert.strictEqual(C.toward(far, B).ok, 3);
assert(Math.abs(C.toward(far, B).medKm - 35.7) < 1, "median km of the toward-B rides");
assert.strictEqual(C.toward(west, B).medKm, null);

const raw = [A, B];
const [line, cum] = C.densify(raw);
const near = C.nearRoute([west, east, spot(50.0, 10.7), spot(50.0, 11.4)], line, cum, 3);
const chain = C.newChain(A, B, near, cum[cum.length - 1]);
assert.strictEqual(chain[0].s, east, "departure spot prefers rides toward B, even close to A");
assert(chain.length >= 2 && chain.every((c, i) => i === 0 || c.at > chain[i - 1].at), "ordered along the route");
// old behaviour never offered a spot within 10 km of A
assert(C.oldChain(A, B, near).every((c) => C.km(A, [c.s.lat, c.s.lon]) >= 10));
const now = 1e12, day = 864e5;
const dl = C.driverList(C.nearRoute([spot(50.0, 10.5, { latest_ms: now - 40 * day }), spot(50.01, 11.0, { latest_ms: now - 2 * day }), spot(50.5, 11.0, { latest_ms: now })], line, cum, 3), now, 2);
assert.strictEqual(dl.length, 2, "spots beyond 2 km are dropped");
assert(dl[0].ageDays < dl[1].ageDays && dl[0].detour > 0, "newest first, detour is there-and-back");
console.log("ok");

// First stop prefers a spot near A over a slightly better-scored one ~14 km out (-0.2 score per km).
{
  const closeSpot = spot(50.0, 10.02, { dest_lats: [50.0], dest_lons: [11.0], rating: 3 });
  const farBetter = spot(50.0, 10.2, { dest_lats: [50.0], dest_lons: [11.0], rating: 5, review_count: 8 }); // ~14 km east of A
  const nr = C.nearRoute([closeSpot, farBetter], line, cum, 3);
  assert.strictEqual(C.newChain(A, B, nr, cum[cum.length - 1])[0].s, closeSpot, "near-A spot wins the first stop");
}

// Evidence floor: a stop with >= MIN_EVIDENCE rides toward B beats a higher-rated one with fewer.
{
  const toward = (n) => ({ dest_lats: Array(n).fill(50.0), dest_lons: Array(n).fill(11.0) });
  const solid = spot(50.0, 10.05, Object.assign({ rating: 2 }, toward(C.MIN_EVIDENCE)));
  const thin = spot(50.0, 10.04, Object.assign({ rating: 5 }, toward(1)));
  const [l2, c2] = C.densify([A, B]);
  const ch = C.newChain(A, B, C.nearRoute([solid, thin], l2, c2, 3), c2[c2.length - 1]);
  assert.strictEqual(ch[0].s, solid, "evidenced stop wins over thin one");
  assert.strictEqual(ch[0].weak, false);
  assert.strictEqual(C.newChain(A, B, C.nearRoute([thin], l2, c2, 3), c2[c2.length - 1])[0].weak, true, "thin stop is flagged weak");
  console.log("ok evidence");
}

// pickVia: evidenced spot 15-80 km off the main road in the middle of the route; none if too close or thin.
{
  const toB = (n) => ({ dest_lats: Array(n).fill(50.3), dest_lons: Array(n).fill(11.5) });
  const off = spot(50.3, 11.0, toB(C.MIN_EVIDENCE));          // ~36 km north of the A-B line
  const onRoad = spot(50.0, 11.0, toB(5)), thin = spot(50.3, 10.9, toB(1));
  const [l3, c3] = C.densify([A, B]);
  assert.strictEqual(C.pickVia([onRoad, thin], A, B, l3, c3), null);
  assert.strictEqual(C.pickVia([onRoad, thin, off], A, B, l3, c3).s, off);
  console.log("ok via");
}
