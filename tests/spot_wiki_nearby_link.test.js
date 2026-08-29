// The spot pane's distance-labelled "Nearest Hitchwiki article" fallback link
// (summaryText, map.js) -- shown only when a spot has no article/map within the
// 100 m exact-join radius but show.py found one within 15 km (detail.hitchwiki_nearby).
//
// map.js is a browser script and can't be require()d, so slice out just the
// `const hitchwikiNearbyLink = ...` assignment and eval it with a stub `tr`,
// the same trick tests/spot_wiki_excerpt_url.test.js uses.

const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");

const SOURCE = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "map.js"), "utf8");

function renderNearbyLink(data) {
  const start = SOURCE.indexOf("const hitchwikiNearbyLink =");
  assert.ok(start !== -1, "hitchwikiNearbyLink assignment moved or was removed");
  const end = SOURCE.indexOf(": '';", start) + ": '';".length;
  const tr = (s, vars = {}) => s.replace(/\{(\w+)\}/g, (_, k) => vars[k]);
  const factory = new Function("data", "tr", `${SOURCE.slice(start, end)}\nreturn hitchwikiNearbyLink;`);
  return factory(data, tr);
}

test("renders a distance-labelled link when only hitchwiki_nearby is set", () => {
  const html = renderNearbyLink({ hitchwiki_nearby: { url: "https://hitchwiki.org/en/Prague", title: "Prague", km: 11.3 } });
  assert.match(html, /href="https:\/\/hitchwiki\.org\/en\/Prague"/);
  assert.match(html, /Nearest Hitchwiki article: Prague \(~11\.3 km\)/);
});

test("stays empty when an exact article link exists", () => {
  const html = renderNearbyLink({
    hitchwiki_article: "https://hitchwiki.org/en/Prague#X",
    hitchwiki_nearby: { url: "https://hitchwiki.org/en/Prague", title: "Prague", km: 11.3 },
  });
  assert.strictEqual(html, "");
});

test("stays empty when an exact map link exists", () => {
  const html = renderNearbyLink({
    hitchwiki_map: "https://hitchwiki.org/en/Prague",
    hitchwiki_nearby: { url: "https://hitchwiki.org/en/Prague", title: "Prague", km: 11.3 },
  });
  assert.strictEqual(html, "");
});

test("stays empty when there is no nearby article at all", () => {
  assert.strictEqual(renderNearbyLink({}), "");
});
