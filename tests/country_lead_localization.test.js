// B362: the country sheet's lead section tries the map's current UI language's
// Hitchwiki first (getCountryWikiLocalTitle, fetchCountryLead), falling back to
// the always-worked English path on any miss or failure. See
// research/country-sheet-localization-scoping-2026-08-24.md in the automation
// repo for why coverage is intentionally sparse (most (country, language)
// pairs have no verified local article) and why this only ever touches the
// lead section, never the Legality-of-Hitchhiking heading (headings aren't
// parallel across languages).
//
// End-to-end behavior (a real French/German user seeing real local content,
// a country with no local coverage falling back to English) was verified
// against a real local dev server + Playwright, not just these unit tests --
// see the B362 run notes for the actual French/German Germany/France output.

const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");

const SOURCE = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "map.js"), "utf8");

function countryWikiBlock() {
  const start = SOURCE.indexOf("const COUNTRY_WIKI_BASE =");
  const end = SOURCE.indexOf("async function loadCountrySheetLegality");
  assert.ok(start !== -1 && end > start, "map.js's country-wiki block moved or was renamed");
  return SOURCE.slice(start, end);
}

function loadCountryWiki(fetchStub, langStub) {
  const factory = new Function(
    "fetch",
    "window",
    `${countryWikiBlock()}
     return { countryWikiApi, getCountryWikiLocalTitle, fetchCountryLead };`,
  );
  return factory(fetchStub, { __LANG__: langStub });
}

test("countryWikiApi defaults to the English wiki when no base is passed (unchanged callers)", () => {
  const { countryWikiApi } = loadCountryWiki(async () => ({}), "en");
  const url = countryWikiApi("Germany", "&prop=sections");
  assert.ok(url.startsWith("https://hitchwiki.org/en/"), url);
});

test("countryWikiApi uses an explicit base when one is passed", () => {
  const { countryWikiApi } = loadCountryWiki(async () => ({}), "en");
  const url = countryWikiApi("Allemagne", "&prop=wikitext&section=0", "https://hitchwiki.org/fr/");
  assert.ok(url.startsWith("https://hitchwiki.org/fr/"), url);
  assert.ok(url.includes("page=Allemagne"));
});

test("getCountryWikiLocalTitle returns null for English (no local attempt needed)", async () => {
  const { getCountryWikiLocalTitle } = loadCountryWiki(async () => {
    throw new Error("should not fetch for English");
  }, "en");
  assert.strictEqual(await getCountryWikiLocalTitle("DE", "en"), null);
});

test("getCountryWikiLocalTitle returns null for a missing country code or language", async () => {
  const { getCountryWikiLocalTitle } = loadCountryWiki(async () => {
    throw new Error("should not fetch with no cc/lang");
  }, "fr");
  assert.strictEqual(await getCountryWikiLocalTitle(null, "fr"), null);
  assert.strictEqual(await getCountryWikiLocalTitle("DE", null), null);
});

test("getCountryWikiLocalTitle resolves a verified title from the static data file", async () => {
  const fetchStub = async (url) => {
    assert.ok(url.includes("country_wiki_local_titles.json"));
    return { ok: true, json: async () => ({ DE: { fr: "Allemagne" } }) };
  };
  const { getCountryWikiLocalTitle } = loadCountryWiki(fetchStub, "fr");
  assert.strictEqual(await getCountryWikiLocalTitle("DE", "fr"), "Allemagne");
});

test("getCountryWikiLocalTitle returns null (not throws) when the data file itself is unreachable", async () => {
  const fetchStub = async () => {
    throw new Error("network down");
  };
  const { getCountryWikiLocalTitle } = loadCountryWiki(fetchStub, "fr");
  assert.strictEqual(await getCountryWikiLocalTitle("DE", "fr"), null);
});

test("getCountryWikiLocalTitle returns null for a country/language pair with no verified entry", async () => {
  const fetchStub = async () => ({ ok: true, json: async () => ({ DE: { fr: "Allemagne" } }) });
  const { getCountryWikiLocalTitle } = loadCountryWiki(fetchStub, "it");
  assert.strictEqual(await getCountryWikiLocalTitle("FJ", "it"), null);
});

test("fetchCountryLead returns the wikitext on success", async () => {
  const fetchStub = async () => ({
    json: async () => ({ parse: { wikitext: { "*": "Real lead text." } } }),
  });
  const { fetchCountryLead } = loadCountryWiki(fetchStub, "fr");
  assert.strictEqual(await fetchCountryLead("Allemagne", "https://hitchwiki.org/fr/"), "Real lead text.");
});

test("fetchCountryLead returns null (not throws) on a failed or empty fetch", async () => {
  const emptyFetch = async () => ({ json: async () => ({}) });
  const { fetchCountryLead: f1 } = loadCountryWiki(emptyFetch, "fr");
  assert.strictEqual(await f1("Allemagne", "https://hitchwiki.org/fr/"), null);

  const throwingFetch = async () => {
    throw new Error("network down");
  };
  const { fetchCountryLead: f2 } = loadCountryWiki(throwingFetch, "fr");
  assert.strictEqual(await f2("Allemagne", "https://hitchwiki.org/fr/"), null);
});

test("a successfully rendered lead records local, fallback, or English UI outcome", () => {
  const block = countryWikiBlock();
  assert.match(
    block,
    /const languageOutcome = usedLocalLang \? "local" : \(lang && lang !== "en" \? "english-fallback" : "english-ui"\);/,
  );
  assert.match(block, /if \(html\) \{[\s\S]{0,300}hmTrack\("country_wiki_lead_shown", \{ outcome: languageOutcome \}\);/);
});
