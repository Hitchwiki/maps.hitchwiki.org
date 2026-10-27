// Routing-gang trip time model, reach-by-dark and start options.
const assert = require("assert");
const C = require("../hitch/static/routing_gang_chain.js");

const near = (at, lat, lon) => ({ at, s: { lat, lon } });
// 200 km, 150 min drive, stops at km 0 and 100 (area waits 10 and 30 min).
const chain = [near(0, 50, 10), near(100, 50, 11.4)];
const waitAt = (lat, lon) => (lon < 11 ? 10 : 30);
const m = C.timeModel(chain, 200, 150, waitAt);
// each 100 km leg gets round(100/60)-1 = 1 extra ride halfway (global 20 min): rides at km 0, 50, 100, 150
assert.strictEqual(m.rides, 4);
assert.strictEqual(m.total, 150 + 10 + 20 + 30 + 20);
assert.strictEqual(m.lo, m.total * C.FAST);
assert.strictEqual(m.hi, m.total * C.SLOW);
// waiting at the first stop: still km 0 after 5 min; at km 100 after 10 + 20 waits + 75 min of driving
assert.strictEqual(C.kmAt(m, 5), 0);
assert(Math.abs(C.kmAt(m, 105) - 100) < 1e-9);
assert(Math.abs(C.minAt(m, 25) - (10 + 18.75)) < 1e-9);
assert.strictEqual(C.kmAt(m, 1e6), 200);
const r = C.reach(m, 160);
assert(r.likely < r.possible && r.possible <= 200, "a good day gets further than a slow one");
// No stops at all still costs one wait at the start.
assert.strictEqual(C.timeModel([], 50, 40, null).total, 40 + C.GLOBAL_WAIT);

// Sunset in Berlin on 2026-06-21 is about 19:33 UTC (21:33 CEST); on 2026-12-21 about 14:54 UTC.
const ss = (d) => new Date(C.sunset(52.52, 13.405, Date.parse(d)).ms).toISOString().slice(11, 16);
const mins = (hhmm) => +hhmm.slice(0, 2) * 60 + +hhmm.slice(3);
assert(Math.abs(mins(ss("2026-06-21T12:00Z")) - mins("19:33")) <= 4, ss("2026-06-21T12:00Z"));
assert(Math.abs(mins(ss("2026-12-21T12:00Z")) - mins("14:54")) <= 4, ss("2026-12-21T12:00Z"));
assert.strictEqual(C.sunset(78.2, 15.6, Date.parse("2026-06-21T12:00Z")).polar, "day");
assert.strictEqual(C.sunset(78.2, 15.6, Date.parse("2026-12-21T12:00Z")).polar, "night");

// slice/pointAt on a densified line
const [line, cum] = C.densify([[50, 10], [50, 11]]);
const sl = C.slice(line, cum, 10, 30);
assert(Math.abs(C.km(sl[0], sl[sl.length - 1]) - 20) < 0.5);

// Start options: best start first, distinct by >= 1 km, only within 15 km of A.
const A = [50, 10], B = [50, 12];
const sp = (lat, lon, dl) => ({ lat, lon, rating: 4, review_count: 5, dest_lats: dl.map(() => 50), dest_lons: dl });
const nr = C.nearRoute([sp(50, 10.02, [11, 11.5, 11.8]), sp(50, 10.021, [11, 11.5, 11.8]), sp(50, 10.1, [11, 11.2, 11.3]), sp(50, 10.5, [11, 11.5, 11.8])], line.concat(C.densify([[50, 11], B])[0]), cum.concat(C.densify([[50, 11], B])[1].map((x) => x + cum[cum.length - 1])), 3);
const so = C.startOptions(A, B, nr, 3);
assert.strictEqual(so.length, 2, "the twin spot 70 m away and the one 36 km out are skipped");
assert.strictEqual(so[0].s.lon, 10.02);
const ch = C.newChain(A, B, nr, 143, null, so[1]);
assert.strictEqual(ch[0], so[1], "a picked start replaces the default first stop");
console.log("ok");
