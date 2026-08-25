const test = require("node:test");
const assert = require("node:assert");
const PendingRides = require("../hitch/static/pending_rides.js");

const DRESDEN = { lat: 51.0817, lon: 13.73629 };

function ride(over) {
  return Object.assign(
    { id: "d1", spot_id: "51.08170_13.73629", lat: DRESDEN.lat, lon: DRESDEN.lon, rating: 4 },
    over,
  );
}

test("a pending ride at a known spot attaches to that spot", () => {
  const spots = [{ lat: DRESDEN.lat, lon: DRESDEN.lon, spotId: "51.08170_13.73629" }];
  const plan = PendingRides.planPendingMerge([ride()], spots);
  assert.strictEqual(plan.create.length, 0);
  assert.strictEqual(plan.attach.length, 1);
  assert.strictEqual(plan.attach[0].spotId, "51.08170_13.73629");
  assert.strictEqual(plan.attach[0].rides.length, 1);
});

test("a ride metres from a known spot snaps onto it instead of making a twin marker", () => {
  // show.py merges rides within 5 m into one anchor and can group a whole service area,
  // so the spot the cron will file this under is NOT the ride's own rounded coordinate.
  const spots = [{ lat: DRESDEN.lat, lon: DRESDEN.lon, spotId: "51.08170_13.73629" }];
  const nudged = ride({ id: "d2", lat: DRESDEN.lat + 0.0002, spot_id: "51.08190_13.73629" });
  const plan = PendingRides.planPendingMerge([nudged], spots);
  assert.strictEqual(plan.create.length, 0);
  assert.strictEqual(plan.attach[0].spotId, "51.08170_13.73629");
});

test("a ride far from every known spot creates a new one", () => {
  const spots = [{ lat: DRESDEN.lat, lon: DRESDEN.lon, spotId: "51.08170_13.73629" }];
  const far = ride({ id: "d3", lat: 52.51739, lon: 13.39513, spot_id: "52.51739_13.39513" });
  const plan = PendingRides.planPendingMerge([far], spots);
  assert.strictEqual(plan.attach.length, 0);
  assert.strictEqual(plan.create.length, 1);
  assert.strictEqual(plan.create[0].spotId, "52.51739_13.39513");
  assert.strictEqual(plan.create[0].lat, 52.51739);
  assert.strictEqual(plan.create[0].review_count, 1);
  assert.strictEqual(plan.create[0].rating, 4);
});

test("several rides at one new spot become a single marker", () => {
  const plan = PendingRides.planPendingMerge(
    [ride({ id: "a", rating: 5 }), ride({ id: "b", rating: 3 })],
    [],
  );
  assert.strictEqual(plan.create.length, 1);
  assert.strictEqual(plan.create[0].review_count, 2);
  assert.strictEqual(plan.create[0].rating, 4);
});

test("a new spot with no rated ride still gets a marker", () => {
  const plan = PendingRides.planPendingMerge([ride({ rating: null })], []);
  assert.strictEqual(plan.create.length, 1);
  assert.strictEqual(plan.create[0].rating, null);
});

test("an unplaceable pending ride is ignored rather than dropped on null island", () => {
  const plan = PendingRides.planPendingMerge([ride({ lat: null, lon: null })], []);
  assert.strictEqual(plan.attach.length, 0);
  assert.strictEqual(plan.create.length, 0);
});

test("a bad payload never throws", () => {
  for (const bad of [null, undefined, "nope", {}]) {
    const plan = PendingRides.planPendingMerge(bad, null);
    assert.deepStrictEqual(plan, { attach: [], create: [] });
  }
});

test("mergeSpotRides keeps the generated copy once the cron catches up", () => {
  const fromFile = [{ id: "d1", comment: "from the generated file" }];
  const pending = [{ id: "d1", comment: "from the live endpoint" }, { id: "d2", comment: "still pending" }];
  const merged = PendingRides.mergeSpotRides(fromFile, pending);
  assert.strictEqual(merged.length, 2);
  assert.strictEqual(merged.find((r) => r.id === "d1").comment, "from the generated file");
  assert.ok(merged.find((r) => r.id === "d2"));
});

test("mergeSpotRides copes with an absent file (a brand-new spot)", () => {
  const merged = PendingRides.mergeSpotRides([], [{ id: "d2" }]);
  assert.strictEqual(merged.length, 1);
});

test("distanceM is metres, not kilometres or radians", () => {
  const d = PendingRides.distanceM(51.0, 13.0, 51.001, 13.0);
  assert.ok(d > 105 && d < 120, `expected ~111 m, got ${d}`);
});
