// The spot pane's "no Hitchwiki article covers this area yet" prompt (summaryText,
// map.js) -- shown only when a spot has no article/map within 100 m AND no article
// within NEARBY_HITCHWIKI_MAX_KM (15 km) either, i.e. show.py's nearby-article lookup
// found nothing at all (idea #62/#147/#171). Points at Hitchwiki's own search/create
// flow -- no content is authored here, per the 2026-08-25 "never write new content"
// rule.
//
// map.js is a browser script and can't be require()d, so slice out just the
// `const hitchwikiGapPrompt = ...` assignment and eval it with a stub `tr`, the same
// trick tests/spot_wiki_nearby_link.test.js uses.

const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");

const SOURCE = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "map.js"), "utf8");

function renderGapPrompt(data, driverContactByCountry = null) {
  const start = SOURCE.indexOf("const hitchwikiGapPrompt =");
  assert.ok(start !== -1, "hitchwikiGapPrompt assignment moved or was removed");
  const end = SOURCE.indexOf(": '';", start) + ": '';".length;
  const tr = (s, vars = {}) => s.replace(/\{(\w+)\}/g, (_, k) => vars[k]);
  const factory = new Function(
    "data", "tr", "driverContactByCountry",
    `${SOURCE.slice(start, end)}\nreturn hitchwikiGapPrompt;`
  );
  return factory(data, tr, driverContactByCountry);
}

test("renders nothing below the review_count floor even with no coverage at all", () => {
  const html = renderGapPrompt({ review_count: 2 });
  assert.strictEqual(html, "");
});

test("renders the prompt once review_count clears the floor and no coverage exists", () => {
  const html = renderGapPrompt({ review_count: 3 });
  assert.match(html, /id="spot-wiki-gap-link"/);
  assert.match(html, /href="https:\/\/hitchwiki\.org\/en\/index\.php\?title=Special:Search/);
});

test("carries the id the click tracker (spot_wiki_gap_clicked) hooks", () => {
  assert.match(SOURCE, /#spot-wiki-gap-link[\s\S]{0,160}spot_wiki_gap_clicked/);
});

test("stays empty when an exact article link exists", () => {
  const html = renderGapPrompt({ review_count: 5, hitchwiki_article: "https://hitchwiki.org/en/Prague#X" });
  assert.strictEqual(html, "");
});

test("stays empty when an exact map link exists", () => {
  const html = renderGapPrompt({ review_count: 5, hitchwiki_map: "https://hitchwiki.org/en/Prague" });
  assert.strictEqual(html, "");
});

test("stays empty when a nearby (within 15 km) article exists instead", () => {
  const html = renderGapPrompt({
    review_count: 5,
    hitchwiki_nearby: { url: "https://hitchwiki.org/en/Prague", title: "Prague", km: 11.3 },
  });
  assert.strictEqual(html, "");
});

test("pre-fills the search with the country name when known", () => {
  const html = renderGapPrompt(
    { review_count: 5, country: "cz" },
    { cz: { name: "Czechia" } }
  );
  assert.match(html, /search=Czechia/);
});

test("falls back to the spot's own name when no country match is available", () => {
  const html = renderGapPrompt({ review_count: 5, name: "Rest area A1" }, null);
  assert.match(html, /search=Rest%20area%20A1/);
});
