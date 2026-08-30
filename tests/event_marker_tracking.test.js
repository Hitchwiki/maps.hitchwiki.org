// #127: the Hitchwiki event layer had no telemetry, so we could not tell whether
// anyone had ever opened an event marker. openEventSheet now fires an
// `event_opened` Umami event, tagged `standing` for a free-hitchhiker house (no
// end date, or ending more than a year out) vs a dated gathering.
//
// map.js is a browser script and cannot be require()d; isStandingEvent is
// self-contained, so slice it out and eval it, the same trick map_lang_paths uses.

const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");

const SOURCE = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "map.js"), "utf8");

function isStandingEvent() {
  const start = SOURCE.indexOf("function isStandingEvent(ev)");
  assert.ok(start !== -1, "map.js no longer defines isStandingEvent");
  const end = SOURCE.indexOf("\n}", start) + 2;
  return new Function(`${SOURCE.slice(start, end)}\nreturn isStandingEvent;`)();
}

test("a dated gathering ending soon is not standing", () => {
  const fn = isStandingEvent();
  const soon = new Date(Date.now() + 14 * 24 * 3600 * 1000).toISOString().slice(0, 10);
  assert.strictEqual(fn({ end: soon }), false);
});

test("an event with no end date is treated as a standing house", () => {
  const fn = isStandingEvent();
  assert.strictEqual(fn({}), true);
  assert.strictEqual(fn({ end: "" }), true);
  assert.strictEqual(fn({ end: "not-a-date" }), true);
});

test("an event ending more than a year out is standing", () => {
  const fn = isStandingEvent();
  const farOut = new Date(Date.now() + 800 * 24 * 3600 * 1000).toISOString().slice(0, 10);
  assert.strictEqual(fn({ end: farOut }), true);
});

test("openEventSheet fires event_opened", () => {
  assert.ok(
    /hmTrack\("event_opened", \{ has_wiki_page:/.test(SOURCE),
    "openEventSheet no longer fires the event_opened telemetry event",
  );
});
