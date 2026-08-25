// The /<lang> mirror handling in map.js's URL scheme.
//
// A shared /mn/spot/<id> link used to open the bare world map: the path regexes were
// root-anchored, so spotFromUrl() found nothing on any of the 30 language mirrors the
// same page is served under. That empty page is what Google indexed.
//
// map.js is a browser script (Leaflet, DOM), so it cannot be require()d. The URL-scheme
// declarations are self-contained, so slice them out and eval them against a stubbed
// window instead — the same trick CLAUDE.md describes for exercising routing.js.

const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");

const SOURCE = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "map.js"), "utf8");

// From the LANG_PREFIX declaration up to (not including) countryFromUrl, which needs
// nothing else: LANG_PREFIX, appPath, langPath and the three path regexes.
function urlSchemeBlock() {
  const start = SOURCE.indexOf("const LANG_PREFIX =");
  const end = SOURCE.indexOf("function countryFromUrl()");
  assert.ok(start !== -1 && end > start, "map.js no longer has the URL-scheme block");
  const dirRe = /^const DIR_PATH_RE = .*$/m.exec(SOURCE);
  assert.ok(dirRe, "DIR_PATH_RE moved");
  return SOURCE.slice(start, end) + "\n" + dirRe[0];
}

// Evaluate the block as if the page were being served in `lang`, and return its bindings.
function schemeFor(lang, pathname) {
  const window = { __LANG__: lang, location: { pathname } };
  const factory = new Function(
    "window",
    `${urlSchemeBlock()}
     return { LANG_PREFIX, appPath, langPath, SPOT_PATH_RE, COUNTRY_PATH_RE, DIR_PATH_RE };`,
  );
  return factory(window);
}

test("a spot path is recognised under a language prefix, exactly as at the root", () => {
  for (const [lang, pathname] of [
    ["en", "/spot/45.78421_21.21907"],
    ["mn", "/mn/spot/45.78421_21.21907"],
    ["fi", "/fi/spot/45.78421_21.21907"],
  ]) {
    const s = schemeFor(lang, pathname);
    const m = s.SPOT_PATH_RE.exec(s.appPath());
    assert.ok(m, `${pathname} should name a spot`);
    assert.deepStrictEqual([+m[1], +m[2]], [45.78421, 21.21907]);
  }
});

test("country and route paths too", () => {
  const c = schemeFor("de", "/de/country/Germany");
  assert.strictEqual(c.COUNTRY_PATH_RE.exec(c.appPath())[1], "Germany");
  const d = schemeFor("de", "/de/dir/47.55811,7.58783/52.51739,13.39513");
  assert.ok(d.DIR_PATH_RE.test(d.appPath()));
});

test("a two-letter first segment that is not the served language is left alone", () => {
  // appPath strips the prefix this page was served under, never a segment that merely
  // looks like one — /me/rides.gpx must stay /me/rides.gpx.
  const s = schemeFor("en", "/me/rides.gpx");
  assert.strictEqual(s.appPath(), "/me/rides.gpx");
  const fi = schemeFor("fi", "/me/rides.gpx");
  assert.strictEqual(fi.appPath(), "/me/rides.gpx");
});

test("the language root maps to /", () => {
  assert.strictEqual(schemeFor("fi", "/fi").appPath(), "/");
  assert.strictEqual(schemeFor("fi", "/fi/").appPath(), "/");
  assert.strictEqual(schemeFor("en", "/").appPath(), "/");
});

test("langPath puts the visitor's language back when the map writes a URL", () => {
  const fi = schemeFor("fi", "/fi/");
  assert.strictEqual(fi.langPath("/spot/1.00000_2.00000"), "/fi/spot/1.00000_2.00000");
  // The map root keeps its trailing slash: "/fi" only redirects onto "/fi/".
  assert.strictEqual(fi.langPath("/"), "/fi/");
  const en = schemeFor("en", "/");
  assert.strictEqual(en.langPath("/spot/1.00000_2.00000"), "/spot/1.00000_2.00000");
  assert.strictEqual(en.langPath("/"), "/");
});

test("appPath and langPath are inverses on every language", () => {
  for (const lang of ["en", "fi", "mn", "zh"]) {
    const s = schemeFor(lang, "/");
    for (const p of ["/spot/1.00000_2.00000", "/country/Germany", "/light.html", "/"]) {
      assert.strictEqual(s.appPath(s.langPath(p)), p, `${lang} ${p}`);
    }
  }
});
