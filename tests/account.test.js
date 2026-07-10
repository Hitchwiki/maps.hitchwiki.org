const test = require("node:test");
const assert = require("node:assert");

const A = require("../hitch/static/account.js");

test("ridesSummary reports truncation, and pluralises when complete", () => {
  assert.strictEqual(A.ridesSummary(50, 231), "Showing 50 of 231 rides");
  assert.strictEqual(A.ridesSummary(3, 3), "3 rides");
  assert.strictEqual(A.ridesSummary(1, 1), "1 ride");
  assert.strictEqual(A.ridesSummary(0, 0), "0 rides");
});

test("formatInsights rounds distance and turns minutes into hours", () => {
  const s = A.formatInsights({ rides: 42, distance_km: 5312.44, waiting_min: 980, partners: 7 });
  assert.strictEqual(s.rides, "42");
  assert.strictEqual(s.distance, "5,312 km");
  assert.strictEqual(s.waiting, "16 h 20 m");
  assert.strictEqual(s.partners, "7");
});

test("formatInsights keeps sub-hour waits in minutes", () => {
  assert.strictEqual(A.formatInsights({ waiting_min: 45 }).waiting, "45 m");
});

test("formatInsights survives a missing/empty insights object", () => {
  const s = A.formatInsights(undefined);
  assert.strictEqual(s.rides, "0");
  assert.strictEqual(s.distance, "0 km");
  assert.strictEqual(s.waiting, "0 m");
  assert.strictEqual(s.partners, "0");
});

test("rideLabel extracts date, stars and trimmed comment", () => {
  const r = A.rideLabel({ created: "2026-07-01T12:00:00", rating: 4, comment: "  nice driver " });
  assert.strictEqual(r.when, "2026-07-01");
  assert.strictEqual(r.stars, "★★★★");
  assert.strictEqual(r.comment, "nice driver");
});

test("rideLabel tolerates a ride with no rating or comment", () => {
  const r = A.rideLabel({ created: "2026-07-01T12:00:00" });
  assert.strictEqual(r.stars, "");
  assert.strictEqual(r.comment, "");
});
