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
  assert.strictEqual(r.when, "Wed 2026-07-01");
  assert.strictEqual(r.stars, "★★★★");
  assert.strictEqual(r.comment, "nice driver");
});

test("rideLabel tolerates a ride with no rating or comment", () => {
  const r = A.rideLabel({ created: "2026-07-01T12:00:00" });
  assert.strictEqual(r.stars, "");
  assert.strictEqual(r.comment, "");
});

const texts = (entries) => entries.map((e) => e.text);

test("rideStats formats wait and distance, omitting what wasn't recorded", () => {
  assert.deepStrictEqual(texts(A.rideStats({ wait_min: 45, distance_km: 138.9 })), ["45 min", "139 km"]);
  // Over an hour reads as hours + minutes.
  assert.deepStrictEqual(texts(A.rideStats({ wait_min: 95, distance_km: 5312.4 })), ["1 h 35 m", "5,312 km"]);
  // null means "not recorded" — omit it rather than print a misleading 0.
  assert.deepStrictEqual(texts(A.rideStats({ wait_min: null, distance_km: 12 })), ["12 km"]);
  assert.deepStrictEqual(texts(A.rideStats({ wait_min: 20, distance_km: null })), ["20 min"]);
  assert.deepStrictEqual(A.rideStats({}), []);
  // A real zero wait is data, not absence, so it must still render.
  assert.deepStrictEqual(texts(A.rideStats({ wait_min: 0 })), ["0 min"]);
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
    texts(A.rideStats({ created: "2026-07-28 12:00", wait_min: 45, distance_km: 138.9 })),
    ["Tue 2026-07-28", "45 min", "139 km"]
  );
  assert.deepStrictEqual(texts(A.rideStats({ created: "2026-07-28 12:00" })), ["Tue 2026-07-28"]);
});

test("flagEmoji maps an ISO alpha-2 code to regional indicators", () => {
  assert.strictEqual(A.flagEmoji("FR"), "🇫🇷");
  assert.strictEqual(A.flagEmoji("de"), "🇩🇪");
  // Anything that isn't two ASCII letters must not produce stray glyphs.
  assert.strictEqual(A.flagEmoji(""), "");
  assert.strictEqual(A.flagEmoji(null), "");
  assert.strictEqual(A.flagEmoji("USA"), "");
  assert.strictEqual(A.flagEmoji("1A"), "");
});

test("rideRoute prefixes each place with its country flag", () => {
  assert.strictEqual(
    A.rideRoute({ from_place: "Metzeral", from_cc: "FR", to_place: "Mitte", to_cc: "DE" }),
    "🇫🇷 Metzeral → 🇩🇪 Mitte"
  );
  // No country code (older generated file) -> just the name, no gap.
  assert.strictEqual(A.rideRoute({ from_place: "Metzeral", to_place: "Mitte" }), "Metzeral → Mitte");
  assert.strictEqual(A.rideRoute({ from_place: "Metzeral", from_cc: "FR" }), "🇫🇷 Metzeral");
});

test("formatRideDate renders dd - month - yy hh:mm", () => {
  assert.strictEqual(A.formatRideDate("2026-07-28 12:00"), "Tue 28 - July - 26 12:00");
  assert.strictEqual(A.formatRideDate("2026-01-05T09:30:00Z"), "Mon 5 - January - 26 09:30");
  // Date only, no time component.
  assert.strictEqual(A.formatRideDate("2026-12-31"), "Thu 31 - December - 26");
  // Garbage in, nothing out — never "NaN - undefined".
  assert.strictEqual(A.formatRideDate(""), "");
  assert.strictEqual(A.formatRideDate(null), "");
  assert.strictEqual(A.formatRideDate("not a date"), "");
  assert.strictEqual(A.formatRideDate("2026-13-01"), "");
});

test("formatRideDate does not shift the day across timezones", () => {
  // new Date("2026-07-28 00:30") would be re-read in the browser's zone and could land on
  // the 27th. `created` is already local submission time, so it is parsed literally.
  assert.strictEqual(A.formatRideDate("2026-07-28 00:30"), "Tue 28 - July - 26 00:30");
  assert.strictEqual(A.formatRideDate("2026-07-28 23:45"), "Tue 28 - July - 26 23:45");
});

test("rideTitle falls back to the date when no place names exist yet", () => {
  assert.strictEqual(
    A.rideTitle({ from_place: "Metzeral", from_cc: "FR", to_place: "Mitte", to_cc: "DE", created: "2026-07-28 12:00" }),
    "🇫🇷 Metzeral → 🇩🇪 Mitte"
  );
  // Not geocoded yet -> the date identifies the ride.
  assert.strictEqual(A.rideTitle({ created: "2026-07-28 12:00" }), "Tue 28 - July - 26 12:00");
  // Neither -> a last-resort label, never an empty row.
  assert.strictEqual(A.rideTitle({}), "Unknown ride");
});

test("rideStats omits the date when the date is already the title", () => {
  const ride = { created: "2026-07-28 12:00", wait_min: 45, distance_km: 138.9 };
  assert.deepStrictEqual(texts(A.rideStats(ride, true)), ["Tue 2026-07-28", "45 min", "139 km"]);
  // Date serving as the title -> don't repeat it below.
  assert.deepStrictEqual(texts(A.rideStats(ride, false)), ["45 min", "139 km"]);
});

test("routeSegments distinguishes a known, missing and never-reached destination", () => {
  // Known destination.
  assert.deepStrictEqual(
    A.routeSegments({ from_place: "Metzeral", from_cc: "FR", to_place: "Mitte", to_cc: "DE" }),
    { start: "🇫🇷 Metzeral", end: "🇩🇪 Mitte", endKind: "place" }
  );
  // Real ride, no destination recorded -> fixable, rendered as an inline warning.
  assert.deepStrictEqual(
    A.routeSegments({ from_place: "Metzeral", from_cc: "FR", missing_destination: true }),
    { start: "🇫🇷 Metzeral", end: "", endKind: "missing" }
  );
  // Give-up: never picked up, so no destination is correct. Not an error.
  assert.deepStrictEqual(
    A.routeSegments({ from_place: "Soultzeren", from_cc: "FR", gave_up: true }),
    { start: "🇫🇷 Soultzeren", end: "gave up", endKind: "gaveup" }
  );
  // A give-up must never be flagged as missing, even if both flags somehow arrived.
  assert.strictEqual(
    A.routeSegments({ from_place: "X", gave_up: true, missing_destination: true }).endKind,
    "gaveup"
  );
});

test("routeSegments falls back to the date when the origin isn't geocoded", () => {
  // No place names yet: the date carries the row, and the arrow must not dangle.
  assert.deepStrictEqual(
    A.routeSegments({ created: "2026-07-28 12:00" }),
    { start: "Tue 28 - July - 26 12:00", end: "", endKind: null }
  );
  // Still flags a missing destination even without an origin name.
  assert.strictEqual(
    A.routeSegments({ created: "2026-07-28 12:00", missing_destination: true }).endKind,
    "missing"
  );
});

test("rideViewUrl links every ride, editable or not", () => {
  // The detail page is public, so even rides the user cannot edit are viewable.
  assert.strictEqual(A.rideViewUrl({ type: "own", d_tag: "abc" }), "/ride/abc");
  assert.strictEqual(A.rideViewUrl({ type: "own_external", d_tag: "abc" }), "/ride/abc");
  assert.strictEqual(A.rideViewUrl({ type: "co_hitchhiker", d_tag: "abc" }), "/ride/abc");
  // d_tags come from Nostr and are not URL-safe by construction.
  assert.strictEqual(A.rideViewUrl({ type: "own", d_tag: "a b&c" }), "/ride/a%20b%26c");
  // No d_tag -> nothing to open.
  assert.strictEqual(A.rideViewUrl({ type: "own" }), null);
});

test("rideStats tags wait as stopped (red) and ride time as going (green)", () => {
  const entries = A.rideStats({ created: "2026-07-28 12:00", wait_min: 45, ride_min: 140, distance_km: 138.9 });
  assert.deepStrictEqual(entries, [
    { text: "Tue 2026-07-28", dot: null },
    { text: "45 min", dot: "stopped" },
    { text: "2 h 20 m", dot: "going" },
    { text: "139 km", dot: null },
  ]);
});

test("rideStats silently omits a ride time the record never carried", () => {
  // The historic form doesn't record arrival, so most rides have no duration at all.
  const entries = A.rideStats({ wait_min: 45, ride_min: null, distance_km: 10 });
  assert.deepStrictEqual(entries.map((e) => e.dot), ["stopped", null]);
  // Nothing recorded at all -> nothing rendered, no empty dots.
  assert.deepStrictEqual(A.rideStats({ created: "" }), []);
  // A zero-minute ride is data, not absence.
  assert.deepStrictEqual(A.rideStats({ ride_min: 0 }), [{ text: "0 min", dot: "going" }]);
});

test("badgeCount shows the number and caps at 99+", () => {
  assert.strictEqual(A.badgeCount(1), "1");
  assert.strictEqual(A.badgeCount(8), "8");
  assert.strictEqual(A.badgeCount(99), "99");
  assert.strictEqual(A.badgeCount(100), "99+");
  assert.strictEqual(A.badgeCount(1247), "99+");
  // Nothing to show below 1.
  assert.strictEqual(A.badgeCount(0), "");
  assert.strictEqual(A.badgeCount(-3), "");
});
