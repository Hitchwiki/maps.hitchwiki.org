const test = require("node:test");
const assert = require("node:assert");
const RideSubmit = require("../hitch/static/ride_submit.js");

const J = {
  pickup: { lat: 48.2, lon: 16.37 },
  gotRideMs: new Date(2026, 6, 2, 14, 0).getTime(),
  finalWaitMs: 12 * 60000,
  details: {
    rating: 4,
    signal: ["thumb"],
    comment: "nice",
    vehicle_kind: "van",
    commercial: false,
    driver_reason_to_pick_up: ["curiosity"],
    driver_gender: "female",
    driver_age: 34,
    driver_origin_country: "DE",
    driver_languages: ["deu", "eng"],
    vehicle_make: "Toyota",
    vehicle_model: "Hiace",
    vehicle_license_plate_country: "DE",
  },
};

test("buildFinishBody carries every demographic field", () => {
  const dest = { lat: 48.5, lon: 16.9 };
  const finishMs = new Date(2026, 6, 2, 14, 41).getTime();
  const body = RideSubmit.buildFinishBody(J, dest, finishMs, "abc-123");

  assert.strictEqual(body.rate, "4");
  assert.strictEqual(body.wait, "12");
  assert.strictEqual(body.signal, "thumb");
  assert.strictEqual(body.datetime_ride, "2026-07-02T14:00");
  assert.strictEqual(body.arrival_datetime, "2026-07-02T14:41");
  assert.strictEqual(body.client_d_tag, "abc-123");
  assert.strictEqual(body.driver_reason_to_pick_up, "curiosity");
  assert.strictEqual(body.driver_gender, "female");
  assert.strictEqual(body.driver_age, "34");
  assert.strictEqual(body.driver_origin_country, "DE");
  assert.strictEqual(body.driver_languages, "deu,eng");
  assert.strictEqual(body.vehicle_make, "Toyota");
  assert.strictEqual(body.vehicle_model, "Hiace");
  assert.strictEqual(body.vehicle_license_plate_country, "DE");
  assert.strictEqual(body.vehicle_commercial, "false");
});

test("absent demographic fields serialize to empty strings", () => {
  const body = RideSubmit.buildFinishBody(
    { pickup: { lat: 1, lon: 2 }, gotRideMs: Date.now(), finalWaitMs: 0, details: { rating: 3 } },
    { lat: 3, lon: 4 }, Date.now(), "id1"
  );
  assert.strictEqual(body.driver_gender, "");
  assert.strictEqual(body.driver_languages, "");
  assert.strictEqual(body.vehicle_commercial, "");
});
