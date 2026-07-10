const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const RideScore = require("../hitch/static/ride_score.js");
const WEIGHTS = JSON.parse(
  fs.readFileSync(path.join(__dirname, "../hitch/static/ride_score_weights.json"), "utf8")
);

test("empty ride scores zero on both meters", () => {
  const s = RideScore.computeScores({}, WEIGHTS);
  assert.strictEqual(s.driver.earned, 0);
  assert.strictEqual(s.driver.max, 60);
  assert.strictEqual(s.driver.pct, 0);
  assert.strictEqual(s.vehicle.earned, 0);
  // No kind chosen -> not passenger -> make/model excluded -> base-only max 40.
  assert.strictEqual(s.vehicle.max, 40);
  assert.strictEqual(s.vehicle.bonusEligible, false);
});

test("full driver detail earns 60 and 100%", () => {
  const s = RideScore.computeScores({
    driver_reason_to_pick_up: ["curiosity"],
    driver_gender: "female",
    driver_age: 34,
    driver_origin_country: "DE",
    driver_languages: ["deu", "eng"],
  }, WEIGHTS);
  assert.strictEqual(s.driver.earned, 60);
  assert.strictEqual(s.driver.pct, 100);
  assert.deepStrictEqual(s.driver.missing, []);
});

test("commercial=false still counts as answered", () => {
  const s = RideScore.computeScores({ vehicle_kind: "bus", commercial: false }, WEIGHTS);
  // bus not passenger -> max 40 (kind 10 + commercial 10 + plate 20)
  assert.strictEqual(s.vehicle.max, 40);
  assert.strictEqual(s.vehicle.earned, 20); // kind 10 + commercial 10
  assert.strictEqual(s.vehicle.bonusEligible, false);
});

test("passenger kind unlocks make/model bonus in max and missing", () => {
  const s = RideScore.computeScores({ vehicle_kind: "car" }, WEIGHTS);
  assert.strictEqual(s.vehicle.bonusEligible, true);
  assert.strictEqual(s.vehicle.max, 50); // 40 base + 10 bonus
  assert.strictEqual(s.vehicle.earned, 10); // kind only
  // Missing ordered by points desc; plate country (20) first.
  assert.deepStrictEqual(
    s.vehicle.missing.map((m) => m.field),
    ["vehicle_license_plate_country", "commercial", "vehicle_make", "vehicle_model"]
  );
});

test("total sums driver + vehicle earned including bonus", () => {
  const s = RideScore.computeScores({
    driver_reason_to_pick_up: ["curiosity"], // 15
    vehicle_kind: "car",                     // 10
    vehicle_make: "Toyota",                  // +5 bonus
  }, WEIGHTS);
  assert.strictEqual(s.total, 30);
});

test("combined pct is total over the whole driver+vehicle pool", () => {
  // Empty: 0 of 100 (no kind -> base-only vehicle max 40).
  assert.strictEqual(RideScore.computeScores({}, WEIGHTS).pct, 0);
  assert.strictEqual(RideScore.computeScores({}, WEIGHTS).maxTotal, 100);

  // Full driver only (60), no kind -> 60 of 100 -> 60%.
  const driverOnly = RideScore.computeScores({
    driver_reason_to_pick_up: ["curiosity"], driver_gender: "female", driver_age: 34,
    driver_origin_country: "DE", driver_languages: ["deu"],
  }, WEIGHTS);
  assert.strictEqual(driverOnly.maxTotal, 100);
  assert.strictEqual(driverOnly.pct, 60);

  // Everything filled on a passenger kind -> 110 of 110 -> 100%.
  const full = RideScore.computeScores({
    driver_reason_to_pick_up: ["curiosity"], driver_gender: "female", driver_age: 34,
    driver_origin_country: "DE", driver_languages: ["deu"],
    vehicle_kind: "car", commercial: false, vehicle_license_plate_country: "DE",
    vehicle_make: "Toyota", vehicle_model: "Yaris",
  }, WEIGHTS);
  assert.strictEqual(full.maxTotal, 110);
  assert.strictEqual(full.pct, 100);
});
