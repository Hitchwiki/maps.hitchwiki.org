// Pure completeness-scoring library shared by the browser (window.RideScore) and
// Node tests (module.exports). Weights are supplied by the caller from the single
// canonical source hitch/static/ride_score_weights.json — never hard-coded here.
(function (root, factory) {
  const mod = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = mod;
  else root.RideScore = mod;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // A field is "filled" when the user has supplied a real answer. Arrays need a
  // non-empty entry; strings need non-whitespace; age accepts a number or numeric
  // string; commercial is a tri-state where BOTH true and false count as answered
  // (only null/undefined is unanswered).
  function isFilled(field, value) {
    if (field === "commercial") return value === true || value === false;
    if (Array.isArray(value)) return value.length > 0;
    if (field === "driver_age") return value !== null && value !== undefined && String(value).trim() !== "";
    return typeof value === "string" && value.trim() !== "";
  }

  function scoreGroup(fields, weightMap) {
    let earned = 0, max = 0;
    const missing = [];
    for (const field of Object.keys(weightMap)) {
      const pts = weightMap[field];
      max += pts;
      if (isFilled(field, fields[field])) earned += pts;
      else missing.push({ field: field, pts: pts });
    }
    return { earned, max, missing };
  }

  function computeScores(fields, weights) {
    fields = fields || {};
    const driver = scoreGroup(fields, weights.driver);
    const driverPct = driver.max ? Math.round((driver.earned / driver.max) * 100) : 0;

    const base = scoreGroup(fields, weights.vehicle_base);
    const bonusEligible = weights.passenger_kinds.indexOf(fields.vehicle_kind) !== -1;
    let vEarned = base.earned, vMax = base.max;
    const vMissing = base.missing.slice();
    if (bonusEligible) {
      const bonus = scoreGroup(fields, weights.vehicle_bonus);
      vEarned += bonus.earned;
      vMax += bonus.max;
      for (const m of bonus.missing) vMissing.push(m);
    }
    // Highest-value missing first, so nudges surface the biggest wins.
    vMissing.sort((a, b) => b.pts - a.pts);
    driver.missing.sort((a, b) => b.pts - a.pts);
    const vPct = vMax ? Math.round((vEarned / vMax) * 100) : 0;

    // Combined completeness: one number over the whole (driver + vehicle) point pool.
    // The UI shows only this; driver/vehicle stay in the return for backend aggregates.
    const maxTotal = driver.max + vMax;
    const total = driver.earned + vEarned;
    const pct = maxTotal ? Math.round((total / maxTotal) * 100) : 0;

    return {
      driver: { earned: driver.earned, max: driver.max, pct: driverPct, missing: driver.missing },
      vehicle: { earned: vEarned, max: vMax, pct: vPct, missing: vMissing, bonusEligible: bonusEligible },
      total: total,
      maxTotal: maxTotal,
      pct: pct,
    };
  }

  return { computeScores };
});
