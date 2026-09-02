// The spot pane's "Last confirmed: <date>" line (summaryText, map.js) -- idea #238.
// It shows how current a spot's ride evidence is, from the filter-independent
// spot-level latest_ms. It is deliberately NOT a quality signal: stale spots rate
// the same as fresh ones, so this line only dates the data.
//
// map.js is a browser script and can't be require()d, so slice out just the
// `const lastConfirmed = ...` assignment and eval it with stubs, the same trick
// tests/spot_wiki_nearby_link.test.js uses.

const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");

const SOURCE = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "map.js"), "utf8");

function renderLastConfirmed(data) {
  const start = SOURCE.indexOf("const lastConfirmed =");
  assert.ok(start !== -1, "lastConfirmed assignment moved or was removed");
  const end = SOURCE.indexOf(': "";', start) + ': "";'.length;
  const formatRideDate = (iso) => "Wed " + new Date(iso).toISOString().slice(0, 10);
  const factory = new Function("data", "formatRideDate", `${SOURCE.slice(start, end)}\nreturn lastConfirmed;`);
  return factory(data, formatRideDate);
}

test("formats the spot-level latest_ms as a date", () => {
  const ms = Date.parse("2026-08-20T09:00:00Z");
  assert.strictEqual(renderLastConfirmed({ latest_ms: ms }), "Wed 2026-08-20");
});

test("stays empty when latest_ms is missing", () => {
  assert.strictEqual(renderLastConfirmed({}), "");
});

test("stays empty when latest_ms is not finite", () => {
  assert.strictEqual(renderLastConfirmed({ latest_ms: NaN }), "");
  assert.strictEqual(renderLastConfirmed({ latest_ms: null }), "");
});

test("summaryText renders the line into the pane markup, after the histograms and before the links", () => {
  assert.match(SOURCE, /spot-distance-hist[\s\S]{0,200}spot-last-confirmed[\s\S]{0,120}\$\{osmLink\}/);
  assert.match(SOURCE, /tr\("Last confirmed: \{date\}"/);
});
