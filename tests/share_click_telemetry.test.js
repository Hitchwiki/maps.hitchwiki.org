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

test("every share surface carries an explicit data-share-context", () => {
  const shareMacro = fs.readFileSync(
    path.join(__dirname, "..", "hitch", "templates", "_share.html"),
    "utf8",
  );
  assert.match(shareMacro, /data-share-context="\{\{ context \}\}"/);

  const routing = fs.readFileSync(
    path.join(__dirname, "..", "hitch", "static", "routing.js"),
    "utf8",
  );
  assert.match(routing, /class="share-btn" data-share-context="' \+ \(shareCompanion \? "route-companion" : "route"\)/);

  const map = fs.readFileSync(
    path.join(__dirname, "..", "hitch", "templates", "map.html"),
    "utf8",
  );
  for (const ctx of ["spot", "insights", "country", "event", "map-view"]) {
    assert.ok(
      map.includes(`data-share-context="${ctx}"`),
      `map.html missing data-share-context="${ctx}"`,
    );
  }
});

test("exactly one hmTrack call in the click handler, carrying context and method", () => {
  const start = SOURCE.indexOf("var btn = e.target.closest");
  const end = SOURCE.indexOf("</script>", start);
  assert.ok(start !== -1 && end > start, "share-btn click handler moved or was renamed");
  const handler = SOURCE.slice(start, end);
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

function tagShareUrl(origin) {
  const start = SOURCE.indexOf("function tagShareUrl(url, ctx) {");
  assert.ok(start !== -1, "base.html no longer has tagShareUrl()");
  const end = SOURCE.indexOf("\n      }\n", start) + "\n      }".length;
  const block = SOURCE.slice(start, end) + "\nreturn tagShareUrl;";
  return new Function("window", "URL", block)({ location: { origin, href: origin + "/" } }, URL);
}

test("#494: same-origin share links get ?ref=share-<context>, fragment kept", () => {
  const fn = tagShareUrl("https://maps.hitchwiki.org");
  assert.strictEqual(
    fn("https://maps.hitchwiki.org/spot/1_2#map=17/1/2", "spot"),
    "https://maps.hitchwiki.org/spot/1_2?ref=share-spot#map=17/1/2",
  );
});

test("#494: foreign-origin and already-tagged links are left alone", () => {
  const fn = tagShareUrl("https://maps.hitchwiki.org");
  assert.strictEqual(fn("https://hitchwiki.org/en/Berlin", "event"), "https://hitchwiki.org/en/Berlin");
  assert.strictEqual(
    fn("https://maps.hitchwiki.org/x?ref=ride-share", "spot"),
    "https://maps.hitchwiki.org/x?ref=ride-share",
  );
});

test("#494: context is sanitised and the handler uses the tagged url", () => {
  const fn = tagShareUrl("https://maps.hitchwiki.org");
  assert.strictEqual(fn("/a", "we ird!"), "https://maps.hitchwiki.org/a?ref=share-weird");
  assert.match(SOURCE, /tagShareUrl\(btn\.dataset\.shareUrl \|\| window\.location\.href, shareContext\(btn\)\)/);
});
