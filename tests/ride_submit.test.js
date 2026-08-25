const test = require("node:test");
const assert = require("node:assert");
const RideSubmit = require("../hitch/static/ride_submit.js");

const J = {
  pickup: { lat: 48.2, lon: 16.37 },
  gotRideMs: new Date(2026, 6, 2, 14, 0).getTime(),
  finalWaitMs: 12 * 60000,
  wouldRideAgain: true,
  details: {
    rating: 4,
    signal: ["thumb"],
    comment: "nice",
    vehicle_kind: "van",
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
  assert.strictEqual(body.driver_would_ride_again, "yes");
});

test("would_ride_again serializes yes/no/'' from the journey flag", () => {
  const base = { pickup: { lat: 1, lon: 2 }, gotRideMs: Date.now(), finalWaitMs: 0, details: { rating: 3 } };
  const yes = RideSubmit.buildFinishBody({ ...base, wouldRideAgain: true }, { lat: 3, lon: 4 }, Date.now(), "i");
  const no = RideSubmit.buildFinishBody({ ...base, wouldRideAgain: false }, { lat: 3, lon: 4 }, Date.now(), "i");
  const unset = RideSubmit.buildFinishBody(base, { lat: 3, lon: 4 }, Date.now(), "i");
  assert.strictEqual(yes.driver_would_ride_again, "yes");
  assert.strictEqual(no.driver_would_ride_again, "no");
  assert.strictEqual(unset.driver_would_ride_again, "");
});

test("absent demographic fields serialize to empty strings", () => {
  const body = RideSubmit.buildFinishBody(
    { pickup: { lat: 1, lon: 2 }, gotRideMs: Date.now(), finalWaitMs: 0, details: { rating: 3 } },
    { lat: 3, lon: 4 }, Date.now(), "id1"
  );
  assert.strictEqual(body.driver_gender, "");
  assert.strictEqual(body.driver_languages, "");
});

test("buildFinishBody carries co_hitchhiker as CSV", () => {
  const j = {
    pickup: { lat: 1, lon: 2 }, gotRideMs: Date.now(), finalWaitMs: 0,
    coHitchhikers: ["sam", "jo"], details: { rating: 4 },
  };
  const body = RideSubmit.buildFinishBody(j, { lat: 3, lon: 4 }, Date.now(), "id1");
  assert.strictEqual(body.co_hitchhiker, "sam,jo");
});

test("buildFinishBody co_hitchhiker is empty string when none", () => {
  const j = { pickup: { lat: 1, lon: 2 }, gotRideMs: Date.now(), finalWaitMs: 0, details: { rating: 4 } };
  const body = RideSubmit.buildFinishBody(j, { lat: 3, lon: 4 }, Date.now(), "id1");
  assert.strictEqual(body.co_hitchhiker, "");
});

test("buildGiveUpBody builds a destination-less body with co_hitchhiker", () => {
  const j = { pickup: { lat: 5, lon: 6 }, coHitchhikers: ["sam"] };
  const body = RideSubmit.buildGiveUpBody(j, 12, { rating: 3, comment: "cold" }, "gid");
  assert.strictEqual(body.rate, "3");
  assert.strictEqual(body.wait, "12");
  assert.strictEqual(body.comment, "cold");
  assert.strictEqual(body.signal, "");
  assert.strictEqual(body.vehicle_kind, "");
  assert.strictEqual(body.co_hitchhiker, "sam");
  assert.strictEqual(body.no_ride, "1"); // a give-up is a no-ride by definition
  assert.strictEqual(body.pickup_lat, 5);
  assert.strictEqual(body.destination_lat, "");
  assert.strictEqual(body.client_d_tag, "gid");
});

// ── toLatLon ─────────────────────────────────────────────────────────────────
// The in-ride pin pickers used to disagree on their output shape (manualPin returned
// {lat, lon}, setWaitingSpot a Leaflet LatLng). Passing the wrong one to buildFinishBody
// produced destination_lon: undefined, which the backend rejected without a clear error.

test("toLatLon normalises a Leaflet LatLng to {lat, lon}", () => {
  assert.deepStrictEqual(RideSubmit.toLatLon({ lat: 48.2, lng: 16.37 }), { lat: 48.2, lon: 16.37 });
});

test("toLatLon passes a plain {lat, lon} through unchanged", () => {
  assert.deepStrictEqual(RideSubmit.toLatLon({ lat: 48.2, lon: 16.37 }), { lat: 48.2, lon: 16.37 });
});

test("toLatLon prefers lon when an object carries both", () => {
  assert.deepStrictEqual(RideSubmit.toLatLon({ lat: 1, lon: 2, lng: 3 }), { lat: 1, lon: 2 });
});

// Greenwich: lon 0 is falsy, so a `||` fallback would read .lng (undefined) instead and
// submit a ride with no longitude. This is why the implementation tests `!= null`.
test("toLatLon keeps lon 0 rather than falling through to lng", () => {
  assert.deepStrictEqual(RideSubmit.toLatLon({ lat: 51.48, lon: 0 }), { lat: 51.48, lon: 0 });
});

test("toLatLon returns null for a missing point", () => {
  assert.strictEqual(RideSubmit.toLatLon(null), null);
});
