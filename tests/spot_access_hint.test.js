// The spot pane's "How people reached this spot" block (summaryText, map.js) --
// shown only when show.py's _access_hint found a ride comment describing the
// transit/walking approach to the spot (detail.access_hint = {c, id}).
//
// map.js is a browser script and can't be require()d, so slice out just the
// `const accessHint = ...` assignment and eval it with stubs, the same trick
// tests/spot_wiki_nearby_link.test.js uses.

const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");

const SOURCE = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "map.js"), "utf8");

function renderAccessHint(data) {
  const start = SOURCE.indexOf("const accessHint =");
  assert.ok(start !== -1, "accessHint assignment moved or was removed");
  const end = SOURCE.indexOf(": '';", start) + ": '';".length;
  const tr = (s, vars = {}) => s.replace(/\{(\w+)\}/g, (_, k) => vars[k]);
  const escapeHtml = (s) =>
    String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const factory = new Function("data", "tr", "escapeHtml", `${SOURCE.slice(start, end)}\nreturn accessHint;`);
  return factory(data, tr, escapeHtml);
}

test("quotes the comment and links to its ride", () => {
  const html = renderAccessHint({ access_hint: { c: "Take bus 31 to the last stop, then walk 200m north.", id: "abc123" } });
  assert.match(html, /How people reached this spot/);
  assert.match(html, /Take bus 31 to the last stop/);
  assert.match(html, /href="\/ride\/abc123"/);
  assert.match(html, /id="spot-access-hint-link"/);
});

test("escapes HTML in the quoted comment", () => {
  const html = renderAccessHint({ access_hint: { c: "walk past the <script>alert(1)</script> sign", id: "x" } });
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /&lt;script&gt;/);
});

test("renders the quote with no source link when the ride id is missing", () => {
  const html = renderAccessHint({ access_hint: { c: "got off the tram at Hauptbahnhof" } });
  assert.match(html, /got off the tram/);
  assert.doesNotMatch(html, /spot-access-hint-link/);
});

test("stays empty when there is no access hint", () => {
  assert.strictEqual(renderAccessHint({}), "");
  assert.strictEqual(renderAccessHint({ access_hint: {} }), "");
});

test("the click tracker (spot_access_hint_clicked) is wired to the link id", () => {
  assert.match(SOURCE, /#spot-access-hint-link[\s\S]{0,160}spot_access_hint_clicked/);
});

test("spot_access_hint_shown fires from handleMarkerClick when the hint is present", () => {
  assert.match(SOURCE, /access_hint[\s\S]{0,80}spot_access_hint_shown/);
});
