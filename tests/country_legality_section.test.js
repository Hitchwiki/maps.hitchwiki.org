// The country sheet's "Legality of Hitchhiking" block (map.js loadCountrySheetLegality,
// findLegalitySection, and renderCountryWikitext's now-shared heading-drop logic).
//
// This surfaces the wiki's own already-sourced "== Legality of Hitchhiking ==" section
// verbatim -- never a classification this app invents (see research/hitchwiki-legality-
// map-scoping-2026-08-21.md in the automation repo for why that distinction matters).
//
// map.js is a browser script, so slice the self-contained country-wiki block out and
// eval it, the same trick map_lang_paths.test.js uses.

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

function loadCountryWiki() {
  const factory = new Function(
    "fetch",
    `${countryWikiBlock()}
     return { renderCountryWikitext, findHitchhikingSection, findLegalitySection, findTopLevelSection, countryWikiApi };`,
  );
  return factory;
}

test("renderCountryWikitext drops both the redundant Hitchhiking and Legality of Hitchhiking headings", () => {
  const { renderCountryWikitext } = loadCountryWiki()();
  const html = renderCountryWikitext(
    "== Legality of Hitchhiking ==\nHitchhiking itself is legal; only standing on a motorway is restricted.",
  );
  assert.ok(!html.includes("<h4>Legality of Hitchhiking</h4>"), "own heading should be dropped, not double-shown");
  assert.ok(html.includes("Hitchhiking itself is legal"), "prose should still render");
});

test("renderCountryWikitext keeps a real subsection heading inside the legality section", () => {
  const { renderCountryWikitext } = loadCountryWiki()();
  const html = renderCountryWikitext(
    "== Legality of Hitchhiking ==\n=== Fines ===\nUp to €50 for standing on the hard shoulder.",
  );
  assert.ok(html.includes("<h4>Fines</h4>"), "a genuine subsection heading must still show");
});

test("renderCountryWikitext safely shows the wiki's own honest 'not checked' placeholder", () => {
  const { renderCountryWikitext } = loadCountryWiki()();
  const html = renderCountryWikitext(
    "== Legality of Hitchhiking ==\n''The law here has not been checked.'' Nobody has yet read the rules.",
  );
  assert.ok(html.includes("<em>The law here has not been checked.</em>"));
});

test("findLegalitySection finds the section by exact heading, case-insensitively", async () => {
  const sections = [
    { toclevel: 1, line: "Getting In", index: "1" },
    { toclevel: 1, line: "legality of hitchhiking", index: "2" },
    { toclevel: 2, line: "Legality of Hitchhiking", index: "3" }, // wrong level, must not match
  ];
  const fetchStub = async () => ({ json: async () => ({ parse: { sections } }) });
  const { findLegalitySection } = loadCountryWiki()(fetchStub);
  assert.strictEqual(await findLegalitySection("Testland"), "2");
});

test("findLegalitySection returns null when the article has no such section", async () => {
  const sections = [{ toclevel: 1, line: "Hitchhiking", index: "1" }];
  const fetchStub = async () => ({ json: async () => ({ parse: { sections } }) });
  const { findLegalitySection } = loadCountryWiki()(fetchStub);
  assert.strictEqual(await findLegalitySection("Testland"), null);
});

test("findLegalitySection returns null (not throws) when the fetch itself fails", async () => {
  const fetchStub = async () => {
    throw new Error("network down");
  };
  const { findLegalitySection } = loadCountryWiki()(fetchStub);
  assert.strictEqual(await findLegalitySection("Testland"), null);
});

test("findHitchhikingSection and findLegalitySection never match each other's heading", async () => {
  const sections = [
    { toclevel: 1, line: "Hitchhiking", index: "1" },
    { toclevel: 1, line: "Legality of Hitchhiking", index: "2" },
  ];
  const fetchStub = async () => ({ json: async () => ({ parse: { sections } }) });
  const bindings = loadCountryWiki()(fetchStub);
  assert.strictEqual(await bindings.findHitchhikingSection("Testland"), "1");
  assert.strictEqual(await bindings.findLegalitySection("Testland"), "2");
});
