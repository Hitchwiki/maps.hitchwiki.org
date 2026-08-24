// parseSpotWikiUrl (map.js), the URL parser behind the spot pane's Hitchwiki
// excerpt (loadSpotWikiExcerpt) -- see the comment above spotWikiExcerptCache
// in map.js for why a spot's hitchwiki_article/hitchwiki_map link carries the
// exact section anchor, not just the article title.
//
// map.js is a browser script (Leaflet, DOM), so it cannot be require()d. Slice
// out COUNTRY_WIKI_BASE + parseSpotWikiUrl and eval them, the same trick
// tests/map_lang_paths.test.js uses for the URL-scheme block.

const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");

const SOURCE = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "map.js"), "utf8");

function loadParseSpotWikiUrl() {
  const baseStart = SOURCE.indexOf("const COUNTRY_WIKI_BASE =");
  const baseLine = /^const COUNTRY_WIKI_BASE = .*$/m.exec(SOURCE.slice(baseStart));
  assert.ok(baseLine, "COUNTRY_WIKI_BASE moved");

  const fnStart = SOURCE.indexOf("function parseSpotWikiUrl(url) {");
  assert.ok(fnStart !== -1, "parseSpotWikiUrl moved or was removed");
  const fnEnd = SOURCE.indexOf("\n}", fnStart) + 2;

  const factory = new Function(`${baseLine[0]}\n${SOURCE.slice(fnStart, fnEnd)}\nreturn parseSpotWikiUrl;`);
  return factory();
}

test("a URL with a section anchor splits into title and decoded anchor", () => {
  const parseSpotWikiUrl = loadParseSpotWikiUrl();
  const result = parseSpotWikiUrl("https://hitchwiki.org/en/Luxembourg (City)#Motorway_exit_for_Brussels");
  assert.deepStrictEqual(result, { title: "Luxembourg (City)", anchor: "Motorway_exit_for_Brussels" });
});

test("a URL with no anchor (hitchwiki_map, article-level) has a null anchor", () => {
  const parseSpotWikiUrl = loadParseSpotWikiUrl();
  const result = parseSpotWikiUrl("https://hitchwiki.org/en/Luxembourg (City)");
  assert.deepStrictEqual(result, { title: "Luxembourg (City)", anchor: null });
});

test("a percent-encoded anchor is decoded back to real text", () => {
  const parseSpotWikiUrl = loadParseSpotWikiUrl();
  const result = parseSpotWikiUrl("https://hitchwiki.org/en/Berlin#Getting%20out");
  assert.deepStrictEqual(result, { title: "Berlin", anchor: "Getting out" });
});
