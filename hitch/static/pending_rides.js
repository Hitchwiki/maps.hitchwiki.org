// Pure merge rules for /pending_rides.json — the rides logged since show.py last
// generated the map files. Kept out of map.js so they are unit-testable under Node
// (no browser is available on the prod host). Browser: window.PendingRides;
// Node: module.exports. Same dual-export shape as ride_submit.js.
(function (root, factory) {
  const mod = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = mod;
  else root.PendingRides = mod;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // How far a pending ride may sit from an existing marker and still be treated as
  // belonging to it. A pending ride carries its RAW pickup coordinate, while spots.json
  // carries the anchor show.py merged it into (5 m merge radius, then service-area /
  // road-island polygon grouping). Without a snap, a ride at a well-known spot would
  // draw a second marker a few metres away that vanishes at the next cron run.
  const SNAP_METRES = 50;

  const EARTH_RADIUS_M = 6371000;

  function distanceM(aLat, aLon, bLat, bLon) {
    const toRad = Math.PI / 180;
    const dLat = (bLat - aLat) * toRad;
    const dLon = (bLon - aLon) * toRad;
    const h =
      Math.sin(dLat / 2) ** 2 +
      Math.cos(aLat * toRad) * Math.cos(bLat * toRad) * Math.sin(dLon / 2) ** 2;
    return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(h));
  }

  function isPlaceable(ride) {
    return (
      ride &&
      typeof ride.lat === "number" &&
      typeof ride.lon === "number" &&
      Number.isFinite(ride.lat) &&
      Number.isFinite(ride.lon)
    );
  }

  function nearestSpot(ride, spots) {
    let best = null;
    let bestDistance = SNAP_METRES;
    for (const spot of spots) {
      const d = distanceM(ride.lat, ride.lon, spot.lat, spot.lon);
      if (d <= bestDistance) {
        bestDistance = d;
        best = spot;
      }
    }
    return best;
  }

  function meanRating(rides) {
    const ratings = rides.map((r) => r.rating).filter((r) => typeof r === "number");
    if (!ratings.length) return null;
    return ratings.reduce((a, b) => a + b, 0) / ratings.length;
  }

  // Split pending rides into those that belong to a marker already on the map and those
  // that need one. `spots` is [{lat, lon, spotId}] — whatever is currently drawn.
  function planPendingMerge(pending, spots) {
    const result = { attach: [], create: [] };
    if (!Array.isArray(pending)) return result;
    const known = Array.isArray(spots) ? spots : [];

    const attachGroups = new Map();
    const createGroups = new Map();

    for (const ride of pending) {
      if (!isPlaceable(ride)) continue;
      const spot = nearestSpot(ride, known);
      if (spot) {
        if (!attachGroups.has(spot.spotId)) attachGroups.set(spot.spotId, []);
        attachGroups.get(spot.spotId).push(ride);
      } else {
        // Rides at a genuinely new place group by their own spot id. Two rides logged
        // a few metres apart within one cron window would draw two markers; that is
        // rare enough to accept rather than reimplement show.py's clustering here.
        if (!createGroups.has(ride.spot_id)) createGroups.set(ride.spot_id, []);
        createGroups.get(ride.spot_id).push(ride);
      }
    }

    for (const [spotId, rides] of attachGroups) result.attach.push({ spotId, rides });
    for (const [spotId, rides] of createGroups) {
      result.create.push({
        spotId: spotId,
        lat: rides[0].lat,
        lon: rides[0].lon,
        rating: meanRating(rides),
        review_count: rides.length,
        rides: rides,
      });
    }
    return result;
  }

  // Combine a spot's generated ride list with its pending ones. The generated copy wins
  // on a tie: during the overlap window (files regenerated, this page's pending list
  // fetched before that) the same ride is in both, keyed by its d tag.
  function mergeSpotRides(fileRides, pendingRides) {
    const merged = Array.isArray(fileRides) ? fileRides.slice() : [];
    const seen = new Set(merged.map((r) => r.id));
    for (const ride of pendingRides || []) {
      if (!seen.has(ride.id)) merged.push(ride);
    }
    return merged;
  }

  return { SNAP_METRES, distanceM, planPendingMerge, mergeSpotRides };
});
