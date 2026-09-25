// Cohort matching for /hitchhiking-safety (hitch/static/safety_stats.js).
//
// The matching rules are the page's whole claim: "two women, alone" has to mean two
// different people and nobody else in the car, and a narrowed age band must not quietly
// sweep in the ~40% of hitchhikers whose age was never recorded.
const test = require("node:test");
const assert = require("node:assert");

const S = require("../hitch/static/safety_stats.js");

const ride = (people, extra) => Object.assign({ w: 1, p: people }, extra || {});
const anyone = () => ({ genders: [], ageMin: null, ageMax: null, expMin: null, expMax: null });

test("an empty filter matches every ride", () => {
  assert.equal(S.matchCohort(ride([["male", 30, 5]]), [anyone()], false), true);
  assert.equal(S.matchCohort(ride([[null, null, null]]), [], false), true);
});

test("a gender filter matches the recorded gender", () => {
  const solo = ride([["female", 22, 3]]);
  assert.equal(S.matchCohort(solo, [{ genders: ["female"] }], false), true);
  assert.equal(S.matchCohort(solo, [{ genders: ["male"] }], false), false);
});

test("'unknown' selects hitchhikers whose gender was never recorded", () => {
  assert.equal(S.matchCohort(ride([[null, 22, null]]), [{ genders: ["unknown"] }], false), true);
  assert.equal(S.matchCohort(ride([["male", 22, null]]), [{ genders: ["unknown"] }], false), false);
});

test("two filters must match two different hitchhikers", () => {
  const two = [{ genders: ["female"] }, { genders: ["female"] }];
  // One woman cannot satisfy "two women", however well she matches both filters.
  assert.equal(S.matchCohort(ride([["female", 25, 1]]), two, false), false);
  assert.equal(S.matchCohort(ride([["female", 25, 1], ["female", 31, 9]]), two, false), true);
});

test("assignment backtracks instead of taking the first fit", () => {
  // Greedy left-to-right matching gives the 25-year-old woman to the loose filter and
  // then fails; the pair is satisfiable and must be found.
  const filters = [{ genders: ["female"] }, { genders: ["female"], ageMin: 20, ageMax: 30 }];
  const rideRow = ride([["female", 25, 2], ["female", 44, 20]]);
  assert.equal(S.matchCohort(rideRow, filters, false), true);
});

test("'exact' means nobody else was hitchhiking along", () => {
  const solo = [{ genders: ["female"] }];
  assert.equal(S.matchCohort(ride([["female", 25, 1], ["male", 30, 2]]), solo, false), true);
  assert.equal(S.matchCohort(ride([["female", 25, 1], ["male", 30, 2]]), solo, true), false);
  assert.equal(S.matchCohort(ride([["female", 25, 1]]), solo, true), true);
});

test("a narrowed range excludes unrecorded values unless asked for", () => {
  const unknownAge = ride([["female", null, null]]);
  assert.equal(S.matchCohort(unknownAge, [{ genders: [], ageMin: 18, ageMax: 25 }], false), false);
  assert.equal(S.matchCohort(unknownAge, [{ genders: [], ageMin: 18, ageMax: 25, ageUnknownOk: true }], false), true);
  // No bound at all is "anybody", so an unrecorded age still matches.
  assert.equal(S.matchCohort(unknownAge, [{ genders: [] }], false), true);
});

test("open-ended bounds work one side at a time", () => {
  assert.equal(S.rangeMatches(70, 60, null, false), true);
  assert.equal(S.rangeMatches(59, 60, null, false), false);
  assert.equal(S.rangeMatches(19, null, 20, false), true);
});

test("wilson interval stays wide on a small all-yes sample", () => {
  const [lo, hi] = S.wilson(4, 4);
  assert.ok(lo < 0.6, `4/4 must not read as near-certain, got ${lo}`);
  assert.ok(hi > 0.999, `upper bound should reach ~1, got ${hi}`);
  assert.equal(S.wilson(0, 0), null);
});

test("summarise counts people, not the Anonymous sentinel", () => {
  const rides = [
    { w: 1, u: ["Anonymous"] },
    { w: 0, u: ["Ada"] },
    { w: 1, u: ["Ada", "Bo"] },
  ];
  const stats = S.summarise(rides);
  assert.deepEqual([stats.rides, stats.yes, stats.no, stats.people], [3, 2, 1, 2]);
});

test("breakdown fans a ride out over list-valued keys", () => {
  const rides = [{ w: 1, s: ["thumb", "sign"] }, { w: 0, s: ["thumb"] }, { w: 1 }];
  const rows = S.breakdown(rides, (r) => r.s || null).sort((a, b) => a.key.localeCompare(b.key));
  assert.deepEqual(rows.map((r) => [r.key, r.rides, r.yes]), [["sign", 1, 1], ["thumb", 2, 1]]);
});

test("bands and dayparts leave unrecorded values out", () => {
  assert.equal(S.band(22, S.AGE_BANDS), "20-24");
  assert.equal(S.band(null, S.AGE_BANDS), null);
  assert.equal(S.band(1200, S.DISTANCE_BANDS), "400+ km");
  assert.equal(S.daypart(23), "night");
  assert.equal(S.daypart(5), "night");
  assert.equal(S.daypart(6), "morning");
  assert.equal(S.daypart(null), null);
});
