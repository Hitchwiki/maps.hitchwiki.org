// The `?ref=<tag>` landing-URL attribution capture in base.html.
//
// base.html is a Jinja template with inline <script> blocks, so it cannot be
// require()d. Slice out the ref-capture block and eval it against a stubbed
// window/history/URLSearchParams, the same trick tests/map_lang_paths.test.js
// uses for map.js's URL-scheme block.

const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");

const SOURCE = fs.readFileSync(
  path.join(__dirname, "..", "hitch", "templates", "base.html"),
  "utf8",
);

function refCaptureBlock() {
  const marker = '// `?ref=<tag>` on the landing URL attributes a visit';
  const start = SOURCE.indexOf(marker);
  assert.ok(start !== -1, "base.html no longer has the ref-capture block");
  const scriptStart = SOURCE.lastIndexOf("<script>", start);
  const scriptEnd = SOURCE.indexOf("</script>", start);
  assert.ok(scriptStart !== -1 && scriptEnd > start, "could not find the enclosing <script> tags");
  return SOURCE.slice(scriptStart + "<script>".length, scriptEnd);
}

// Runs the block against a fake location.search, returning what it tracked and
// what it rewrote the URL to (or null for either if it did nothing).
function run(search) {
  const tracked = [];
  let replacedTo = null;
  const window = {
    location: { search: search, pathname: "/some/page", hash: "#map=5/10/10" },
    hmTrack: function (name, data) { tracked.push([name, data]); },
  };
  const history = {
    replaceState: function (state, title, url) { replacedTo = url; },
  };
  const factory = new Function("window", "history", "URLSearchParams", refCaptureBlock());
  factory(window, history, URLSearchParams);
  return { tracked, replacedTo };
}

test("a plain ref tag is tracked and stripped from the address bar", () => {
  const { tracked, replacedTo } = run("?ref=wiki-record-ride");
  assert.deepStrictEqual(tracked, [["referred_via", { ref: "wiki-record-ride" }]]);
  assert.strictEqual(replacedTo, "/some/page#map=5/10/10");
});

test("no ref param: no track call, no URL rewrite", () => {
  const { tracked, replacedTo } = run("?lat=1&lon=2");
  assert.deepStrictEqual(tracked, []);
  assert.strictEqual(replacedTo, null);
});

test("no query string at all: no-op", () => {
  const { tracked, replacedTo } = run("");
  assert.deepStrictEqual(tracked, []);
  assert.strictEqual(replacedTo, null);
});

test("other params survive the rewrite, only ref is removed", () => {
  const { tracked, replacedTo } = run("?ref=tr-hitch-circle-2026-08&lat=52.5");
  assert.deepStrictEqual(tracked, [["referred_via", { ref: "tr-hitch-circle-2026-08" }]]);
  assert.strictEqual(replacedTo, "/some/page?lat=52.5#map=5/10/10");
});

test("sanitisation strips anything but alphanumerics/dash/underscore", () => {
  const { tracked } = run("?ref=" + encodeURIComponent("a<script>b&c=d"));
  assert.deepStrictEqual(tracked, [["referred_via", { ref: "ascriptbcd" }]]);
});

test("sanitisation truncates to 64 characters", () => {
  const long = "a".repeat(100);
  const { tracked } = run("?ref=" + long);
  assert.strictEqual(tracked[0][1].ref.length, 64);
  assert.strictEqual(tracked[0][1].ref, "a".repeat(64));
});

test("a ref value that sanitises to empty is treated as absent", () => {
  const { tracked, replacedTo } = run("?ref=" + encodeURIComponent("!!!"));
  assert.deepStrictEqual(tracked, []);
  assert.strictEqual(replacedTo, null);
});
