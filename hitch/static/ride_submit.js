// Pure /ride POST-body builder for the in-ride Finish flow. Extracted from inride.js
// so it is unit-testable (Node) and reusable by later enrichment phases. Browser:
// window.RideSubmit; Node: module.exports.
(function (root, factory) {
  const mod = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = mod;
  else root.RideSubmit = mod;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // "YYYY-MM-DDTHH:mm" from LOCAL date components — NOT toISOString() (UTC), which
  // would silently offset times by the user's UTC offset.
  function isoLocal(ms) {
    const d = new Date(ms);
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  // Accept either a Leaflet LatLng (.lat/.lng) or a plain {lat, lon}, always return
  // {lat, lon}. The in-ride pin pickers used to disagree on this shape, which once
  // produced destination_lon: undefined in a submitted ride body.
  // `!= null` rather than `||`: lon 0 (Greenwich) is falsy but valid.
  function toLatLon(p) {
    if (!p) return null;
    return { lat: p.lat, lon: p.lon != null ? p.lon : p.lng };
  }

  // Build the /ride form body from a journey + destination. client_d_tag pins the Nostr
  // d_tag so outbox retries replace rather than duplicate. finishMs is captured at the
  // START of journeyFlow.finish() so GPS/manual-pin delay doesn't inflate arrival time.
  function buildFinishBody(j, dest, finishMs, id) {
    const d = j.details || {};
    const csv = (v) => (Array.isArray(v) ? v.join(",") : (v || ""));
    return {
      rate: String(d.rating || ""),
      wait: String(Math.round((j.finalWaitMs || 0) / 60000)),
      signal: csv(d.signal),
      comment: d.comment || "",
      vehicle_kind: d.vehicle_kind || "",
      // Demographic carry-through (Phase 2 UI populates these onto j.details).
      driver_reason_to_pick_up: csv(d.driver_reason_to_pick_up),
      driver_gender: d.driver_gender || "",
      driver_age: (d.driver_age === 0 || d.driver_age) ? String(d.driver_age) : "",
      driver_origin_country: d.driver_origin_country || "",
      driver_languages: csv(d.driver_languages),
      // Forced Yes/No captured at Finish (j.wouldRideAgain); "" only if somehow unset.
      driver_would_ride_again: j.wouldRideAgain === true ? "yes" : (j.wouldRideAgain === false ? "no" : ""),
      vehicle_make: d.vehicle_make || "",
      vehicle_model: d.vehicle_model || "",
      vehicle_license_plate_country: d.vehicle_license_plate_country || "",
      co_hitchhiker: (j.coHitchhikers || []).join(","),
      pickup_lat: j.pickup.lat, pickup_lon: j.pickup.lon,
      destination_lat: dest.lat, destination_lon: dest.lon,
      datetime_ride: isoLocal(j.gotRideMs),
      arrival_datetime: isoLocal(finishMs),
      client_d_tag: id,
    };
  }

  // Destination-less give-up body (rated wait, no ride). Pure so it is unit-testable;
  // co-hitchers who waited together are attached here too.
  function buildGiveUpBody(j, waitMin, details, id) {
    return {
      rate: String(details.rating || ""),
      wait: String(waitMin),
      comment: details.comment || "",
      // Giving up IS a no-ride by definition — same marker the /ride form checkbox sets.
      no_ride: "1",
      signal: "", vehicle_kind: "",
      co_hitchhiker: (j.coHitchhikers || []).join(","),
      pickup_lat: j.pickup.lat, pickup_lon: j.pickup.lon,
      destination_lat: "", destination_lon: "",
      client_d_tag: id,
    };
  }

  return { isoLocal, buildFinishBody, buildGiveUpBody, toLatLon };
});
