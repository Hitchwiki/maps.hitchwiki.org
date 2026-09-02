// #228: the delegated .share-btn handler in base.html now emits one share_click
// event carrying which of the nine share surfaces fired. base.html is a Jinja
// template with {{ t(...) }} in the handler, so we slice out the clean
// shareContext() helper and exercise it directly, and assert-match the rest.

const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");

const SOURCE = fs.readFileSync(
  path.join(__dirname, "..", "hitch", "templates", "base.html"),
  "utf8",
);

function shareContext() {
  const start = SOURCE.indexOf("function shareContext(btn) {");
  assert.ok(start !== -1, "base.html no longer has shareContext()");
  const end = SOURCE.indexOf("\n      }", start) + "\n      }".length;
  const block = SOURCE.slice(start, end) + "\nreturn shareContext;";
  return new Function("window", block)({
    location: { pathname: "/route/foo" },
  });
}

test("explicit data-share-context wins", () => {
  const fn = shareContext();
  assert.strictEqual(
    fn({ dataset: { shareContext: "ride-detail" }, id: "x" }),
    "ride-detail",
  );
});

test("falls back to a cleaned button id", () => {
  const fn = shareContext();
  assert.strictEqual(fn({ dataset: {}, id: "share-spot-btn" }), "spot");
  assert.strictEqual(fn({ dataset: {}, id: "share-country-btn" }), "country");
});

test("falls back to the first path segment with no id", () => {
  const fn = shareContext();
  assert.strictEqual(fn({ dataset: {}, id: "" }), "route");
});

test("exactly one hmTrack call in the click handler, carrying context and method", () => {
  const handler = SOURCE.slice(SOURCE.indexOf("var btn = e.target.closest"));
  const calls = handler.match(/hmTrack\(/g) || [];
  assert.strictEqual(
    calls.length,
    1,
    "expected a single hmTrack call in the share handler",
  );
  assert.match(
    handler,
    /hmTrack\('share_click', \{\s*context: shareContext\(btn\),\s*method: navigator\.share \? 'native' : 'clipboard'/,
  );
});
