const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const RideScore = require("../hitch/static/ride_score.js");
const WEIGHTS = JSON.parse(
  fs.readFileSync(path.join(__dirname, "../hitch/static/ride_score_weights.json"), "utf8")
);

test("empty ride scores zero on both sections", () => {
  const s = RideScore.computeScores({}, WEIGHTS);
  assert.strictEqual(s.driver.earned, 0);
  assert.strictEqual(s.driver.max, 70); // reason 15 + gender 15 + age 20 + origin 10 + languages 10
  assert.strictEqual(s.driver.pct, 0);
  assert.strictEqual(s.vehicle.earned, 0);
  assert.strictEqual(s.vehicle.max, 30); // plate 20 + kind 10 (make/model unscored)
});

test("full driver detail earns 70 and 100%", () => {
  const s = RideScore.computeScores({
    driver_reason_to_pick_up: ["curiosity"],
    driver_gender: "female",
    driver_age: 34,
    driver_origin_country: "DE",
    driver_languages: ["deu", "eng"],
  }, WEIGHTS);
  assert.strictEqual(s.driver.earned, 70);
  assert.strictEqual(s.driver.pct, 100);
  assert.deepStrictEqual(s.driver.missing, []);
});

test("vehicle is base-only: plate + kind, make/model unscored", () => {
  const s = RideScore.computeScores({ vehicle_kind: "bus" }, WEIGHTS);
  assert.strictEqual(s.vehicle.max, 30);
  assert.strictEqual(s.vehicle.earned, 10); // kind only
  assert.deepStrictEqual(s.vehicle.missing.map((m) => m.field), ["vehicle_license_plate_country"]);
});

test("make/model never affect the vehicle max (100% reachable without them)", () => {
  const s = RideScore.computeScores({
    vehicle_kind: "car", vehicle_license_plate_country: "DE",
  }, WEIGHTS);
  assert.strictEqual(s.vehicle.max, 30);
  assert.strictEqual(s.vehicle.earned, 30);
  assert.strictEqual(s.vehicle.pct, 100);
});

test("total sums driver + vehicle earned", () => {
  const s = RideScore.computeScores({
    driver_reason_to_pick_up: ["curiosity"], // 15
    vehicle_kind: "car",                     // 10
  }, WEIGHTS);
  assert.strictEqual(s.total, 25);
});

test("combined pct is total over the whole driver+vehicle pool (always /100)", () => {
  // Empty: 0 of 100.
  assert.strictEqual(RideScore.computeScores({}, WEIGHTS).pct, 0);
  assert.strictEqual(RideScore.computeScores({}, WEIGHTS).maxTotal, 100);

  // Full driver only (70), no vehicle -> 70 of 100 -> 70%.
  const driverOnly = RideScore.computeScores({
    driver_reason_to_pick_up: ["curiosity"], driver_gender: "female", driver_age: 34,
    driver_origin_country: "DE", driver_languages: ["deu"],
  }, WEIGHTS);
  assert.strictEqual(driverOnly.maxTotal, 100);
  assert.strictEqual(driverOnly.pct, 70);

  // Every scored field filled, WITHOUT make/model -> 100 of 100 -> 100%.
  const full = RideScore.computeScores({
    driver_reason_to_pick_up: ["curiosity"], driver_gender: "female", driver_age: 34,
    driver_origin_country: "DE", driver_languages: ["deu"],
    vehicle_kind: "car", vehicle_license_plate_country: "DE",
  }, WEIGHTS);
  assert.strictEqual(full.maxTotal, 100);
  assert.strictEqual(full.pct, 100);
});
