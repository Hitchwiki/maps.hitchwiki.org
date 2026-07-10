const test = require("node:test");
const assert = require("node:assert");

const A = require("../hitch/static/account.js");

test("ridesSummary reports truncation, and pluralises when complete", () => {
  assert.strictEqual(A.ridesSummary(50, 231), "Showing 50 of 231 rides");
  assert.strictEqual(A.ridesSummary(3, 3), "3 rides");
  assert.strictEqual(A.ridesSummary(1, 1), "1 ride");
  assert.strictEqual(A.ridesSummary(0, 0), "0 rides");
});

test("formatInsights rounds distance and turns minutes into hours", () => {
  const s = A.formatInsights({ rides: 42, distance_km: 5312.44, waiting_min: 980, partners: 7 });
  assert.strictEqual(s.rides, "42");
  assert.strictEqual(s.distance, "5,312 km");
  assert.strictEqual(s.waiting, "16 h 20 m");
  assert.strictEqual(s.partners, "7");
});

test("formatInsights keeps sub-hour waits in minutes", () => {
  assert.strictEqual(A.formatInsights({ waiting_min: 45 }).waiting, "45 m");
});

test("formatInsights survives a missing/empty insights object", () => {
  const s = A.formatInsights(undefined);
  assert.strictEqual(s.rides, "0");
  assert.strictEqual(s.distance, "0 km");
  assert.strictEqual(s.waiting, "0 m");
  assert.strictEqual(s.partners, "0");
});

test("rideLabel extracts date, stars and trimmed comment", () => {
  const r = A.rideLabel({ created: "2026-07-01T12:00:00", rating: 4, comment: "  nice driver " });
  assert.strictEqual(r.when, "2026-07-01");
  assert.strictEqual(r.stars, "★★★★");
  assert.strictEqual(r.comment, "nice driver");
});

test("rideLabel tolerates a ride with no rating or comment", () => {
  const r = A.rideLabel({ created: "2026-07-01T12:00:00" });
  assert.strictEqual(r.stars, "");
  assert.strictEqual(r.comment, "");
});

test("rideStats formats wait and distance, omitting what wasn't recorded", () => {
  assert.deepStrictEqual(A.rideStats({ wait_min: 45, distance_km: 138.9 }), ["45 min", "139 km"]);
  // Over an hour reads as hours + minutes.
  assert.deepStrictEqual(A.rideStats({ wait_min: 95, distance_km: 5312.4 }), ["1 h 35 m", "5,312 km"]);
  // null means "not recorded" — omit it rather than print a misleading 0.
  assert.deepStrictEqual(A.rideStats({ wait_min: null, distance_km: 12 }), ["12 km"]);
  assert.deepStrictEqual(A.rideStats({ wait_min: 20, distance_km: null }), ["20 min"]);
  assert.deepStrictEqual(A.rideStats({}), []);
  // A real zero wait is data, not absence, so it must still render.
  assert.deepStrictEqual(A.rideStats({ wait_min: 0 }), ["0 min"]);
});

test("completionPct rounds and clamps, defaulting to 0 when absent", () => {
  assert.strictEqual(A.completionPct({ completion: 100 }), 100);
  assert.strictEqual(A.completionPct({ completion: 24.6 }), 25);
  assert.strictEqual(A.completionPct({ completion: 0 }), 0);
  assert.strictEqual(A.completionPct({}), 0);
  assert.strictEqual(A.completionPct({ completion: 140 }), 100);
  assert.strictEqual(A.completionPct({ completion: -5 }), 0);
});

test("rideEditUrl only links rides the user can actually edit", () => {
  // /ride?edit= only prefills for rides we published — type "own".
  assert.strictEqual(A.rideEditUrl({ type: "own", d_tag: "abc" }), "/ride?edit=abc");
  // Imported from another source: the edit form would not prefill, so no dead link.
  assert.strictEqual(A.rideEditUrl({ type: "own_external", d_tag: "abc" }), null);
  assert.strictEqual(A.rideEditUrl({ type: "co_hitchhiker", d_tag: "abc" }), null);
  assert.strictEqual(A.rideEditUrl({ type: "own" }), null);
  // d_tags come from Nostr and are not URL-safe by construction.
  assert.strictEqual(A.rideEditUrl({ type: "own", d_tag: "a b&c" }), "/ride?edit=a%20b%26c");
});

test("awardsSummary pluralises", () => {
  assert.strictEqual(A.awardsSummary(1), "1 award earned");
  assert.strictEqual(A.awardsSummary(3), "3 awards earned");
});

test("completionTier maps a percentage to a colour band", () => {
  assert.strictEqual(A.completionTier(0), "low");
  assert.strictEqual(A.completionTier(33), "low");
  assert.strictEqual(A.completionTier(34), "mid");
  assert.strictEqual(A.completionTier(66), "mid");
  assert.strictEqual(A.completionTier(67), "high");
  assert.strictEqual(A.completionTier(99), "high");
  // 100 stops being a progress bar and becomes a badge.
  assert.strictEqual(A.completionTier(100), "done");
});

test("ridesNeedingDetails counts only rides the user can actually fix", () => {
  const rides = [
    { type: "own", d_tag: "a", completion: 100 },                          // done
    { type: "own", d_tag: "b", completion: 40 },                           // incomplete
    { type: "own", d_tag: "c", completion: 100, missing_destination: true }, // complete but no dest
    { type: "own_external", d_tag: "d", completion: 0 },                   // not editable
    { type: "co_hitchhiker", d_tag: "e", completion: 0 },                  // not editable
  ];
  assert.strictEqual(A.ridesNeedingDetails(rides), 2);
  assert.strictEqual(A.ridesNeedingDetails([]), 0);
});

test("nudgeText pluralises and rewards a clean sheet", () => {
  assert.strictEqual(A.nudgeText(0), "Every ride is fully logged. Nice.");
  assert.strictEqual(A.nudgeText(1), "1 ride could use more detail");
  assert.strictEqual(A.nudgeText(4), "4 rides could use more detail");
});

test("rideRoute labels a ride by where it went, degrading gracefully", () => {
  assert.strictEqual(A.rideRoute({ from_place: "Metzeral", to_place: "Mitte" }), "Metzeral → Mitte");
  // A give-up has no destination.
  assert.strictEqual(A.rideRoute({ from_place: "Metzeral" }), "Metzeral");
  assert.strictEqual(A.rideRoute({ to_place: "Mitte" }), "→ Mitte");
  // Not geocoded yet (cron hasn't run) -> empty, so the UI shows its fallback.
  assert.strictEqual(A.rideRoute({}), "");
  assert.strictEqual(A.rideRoute({ from_place: "  ", to_place: null }), "");
});

test("rideStats leads with the date, then wait and distance", () => {
  assert.deepStrictEqual(
    A.rideStats({ created: "2026-07-28 12:00", wait_min: 45, distance_km: 138.9 }),
    ["2026-07-28", "45 min", "139 km"]
  );
  assert.deepStrictEqual(A.rideStats({ created: "2026-07-28 12:00" }), ["2026-07-28"]);
});
