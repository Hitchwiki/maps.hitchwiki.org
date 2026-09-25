// Cohort matching and rate arithmetic behind /hitchhiking-safety. Kept out of the page
// script so it is unit-testable under Node (no browser is available on the prod host —
// see CLAUDE.md). Browser: window.SafetyStats; Node: module.exports. Same dual-export
// shape as pending_rides.js.
//
// A ride row is the compact shape hitch/blueprints/utils/safety_statistics.py writes:
//   {w, p: [[gender, age, experience], ...], dg, da, y, h, wt, km, v, s, r, cc, u, n}
// Missing keys mean "not recorded" — the generator drops empty values to keep the file
// the page downloads small, so every read here has to tolerate undefined.
(function (root, factory) {
  const mod = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = mod;
  else root.SafetyStats = mod;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const UNKNOWN = "unknown";

  // A person filter is {genders: [], ageMin, ageMax, ageUnknownOk, expMin, expMax, expUnknownOk}.
  // An empty/absent constraint matches everyone, so a fresh person card is "anybody".
  function personMatches(person, filter) {
    if (!filter) return true;
    const gender = person[0] || UNKNOWN;
    const genders = filter.genders || [];
    if (genders.length && genders.indexOf(gender) === -1) return false;
    if (!rangeMatches(person[1], filter.ageMin, filter.ageMax, filter.ageUnknownOk)) return false;
    if (!rangeMatches(person[2], filter.expMin, filter.expMax, filter.expUnknownOk)) return false;
    return true;
  }

  // A narrowed range excludes people whose value was never recorded, unless the caller
  // opts them back in. The other way round reads as a lie: "hitchhikers aged 18-25"
  // must not silently include the 40% whose age nobody wrote down.
  function rangeMatches(value, min, max, unknownOk) {
    const bounded = min != null || max != null;
    if (value == null) return !bounded || !!unknownOk;
    if (min != null && value < min) return false;
    if (max != null && value > max) return false;
    return true;
  }

  // Each filter must claim a DIFFERENT hitchhiker: "one woman and one man" has to mean
  // two people, not one person counted twice. Rides carry at most 5 hitchhikers and the
  // UI allows at most 4 filters, so exhaustive backtracking is far cheaper than a real
  // matching algorithm and cannot get the answer subtly wrong.
  function assignable(people, filters, used, index) {
    if (index >= filters.length) return true;
    for (let i = 0; i < people.length; i++) {
      if (used[i] || !personMatches(people[i], filters[index])) continue;
      used[i] = true;
      if (assignable(people, filters, used, index + 1)) return true;
      used[i] = false;
    }
    return false;
  }

  // `exact` means the ride had exactly this many hitchhikers and no others — the
  // difference between "two women were in the car" and "two women, alone".
  function matchCohort(ride, filters, exact) {
    const people = ride.p || [[null, null, null]];
    const active = (filters || []).filter(Boolean);
    if (exact && people.length !== Math.max(active.length, 1)) return false;
    if (!active.length) return true;
    if (people.length < active.length) return false;
    return assignable(people, active, new Array(people.length).fill(false), 0);
  }

  // Wilson score interval, 95%. A normal-approximation interval is useless here: most
  // cells are small and many are 100% yes, where it collapses to zero width and would
  // render "certainly safe" out of four rides.
  function wilson(successes, total) {
    if (!total) return null;
    const z = 1.959964;
    const p = successes / total;
    const denominator = 1 + (z * z) / total;
    const centre = p + (z * z) / (2 * total);
    const spread = z * Math.sqrt((p * (1 - p)) / total + (z * z) / (4 * total * total));
    return [Math.max(0, (centre - spread) / denominator), Math.min(1, (centre + spread) / denominator)];
  }

  function summarise(rides) {
    const yes = rides.reduce((sum, ride) => sum + (ride.w ? 1 : 0), 0);
    const names = new Set();
    rides.forEach((ride) => (ride.u || []).forEach((name) => names.add(name)));
    return {
      rides: rides.length,
      yes: yes,
      no: rides.length - yes,
      rate: rides.length ? yes / rides.length : null,
      ci: wilson(yes, rides.length),
      // Distinct named hitchhikers, "Anonymous" excluded: it is a sentinel, not a
      // person (hitch/usernames.py), and counting it as one would read as a crowd.
      people: [...names].filter((name) => name !== "Anonymous").length,
    };
  }

  // keyFn returns a key, a list of keys (a ride can use several signal methods), or
  // null/[] to leave the ride out of this breakdown entirely — "not recorded" is its own
  // row only where the generator can tell absence from a value.
  function breakdown(rides, keyFn) {
    const buckets = new Map();
    rides.forEach((ride) => {
      let keys = keyFn(ride);
      if (keys == null) return;
      if (!Array.isArray(keys)) keys = [keys];
      keys.forEach((key) => {
        if (key == null) return;
        if (!buckets.has(key)) buckets.set(key, []);
        buckets.get(key).push(ride);
      });
    });
    return [...buckets.entries()].map(([key, subset]) => Object.assign({ key: key }, summarise(subset)));
  }

  // Band edges are inclusive lower bounds. Wide on purpose: with ~1.1k answered rides in
  // the whole corpus, finer bands produce rows nobody may read anything into.
  const AGE_BANDS = [
    [0, 20, "under 20"],
    [20, 25, "20-24"],
    [25, 30, "25-29"],
    [30, 40, "30-39"],
    [40, 60, "40-59"],
    [60, Infinity, "60+"],
  ];
  const WAIT_BANDS = [
    [0, 5, "under 5 min"],
    [5, 15, "5-14 min"],
    [15, 30, "15-29 min"],
    [30, 60, "30-59 min"],
    [60, Infinity, "60+ min"],
  ];
  const DISTANCE_BANDS = [
    [0, 10, "under 10 km"],
    [10, 50, "10-49 km"],
    [50, 150, "50-149 km"],
    [150, 400, "150-399 km"],
    [400, Infinity, "400+ km"],
  ];

  function band(value, bands) {
    if (value == null) return null;
    const hit = bands.find(([low, high]) => value >= low && value < high);
    return hit ? hit[2] : null;
  }

  // Night is 21:00-05:59. Hitchhiking after dark is the single time-of-day distinction
  // people actually ask about, so a two-way split beats six thin hourly rows.
  function daypart(hour) {
    if (hour == null) return null;
    if (hour >= 21 || hour < 6) return "night";
    if (hour < 12) return "morning";
    if (hour < 18) return "afternoon";
    return "evening";
  }

  return {
    UNKNOWN: UNKNOWN,
    AGE_BANDS: AGE_BANDS,
    WAIT_BANDS: WAIT_BANDS,
    DISTANCE_BANDS: DISTANCE_BANDS,
    personMatches: personMatches,
    rangeMatches: rangeMatches,
    matchCohort: matchCohort,
    wilson: wilson,
    summarise: summarise,
    breakdown: breakdown,
    band: band,
    daypart: daypart,
  };
});
