// city_wiki_excerpt.js's wikitext-to-HTML transform, the client-side piece of
// B353 (show a city page's Hitchwiki excerpt) -- see city_template.html for
// where this is wired in and why it fetches client-side rather than at build
// time in cities.py.
//
// The file is a standalone browser script (no framework), so stub `window` and
// `document` and eval it, the same trick tests/map_lang_paths.test.js uses for
// map.js.

const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");

const SOURCE = fs.readFileSync(
  path.join(__dirname, "..", "hitch", "static", "city_wiki_excerpt.js"),
  "utf8",
);

function load() {
  const window = {};
  const document = {
    readyState: "complete",
    getElementById: function () {
      return null;
    },
  };
  const factory = new Function("window", "document", SOURCE + "\nreturn window.__cityWikiExcerpt;");
  return factory(window, document);
}

test("plain prose survives untouched, wrapped in a paragraph", () => {
  const { renderExcerpt } = load();
  const html = renderExcerpt("Berlin is a major hitchhiking hub in Germany.");
  assert.strictEqual(html, "<p>Berlin is a major hitchhiking hub in Germany.</p>");
});

test("wikilinks become real links, piped labels keep the display text", () => {
  const { renderExcerpt } = load();
  const html = renderExcerpt("See [[Autobahn]] and [[Berlin Tempelhof Airport|Tempelhof]].");
  assert.match(html, /<a href="https:\/\/hitchwiki\.org\/en\/Autobahn"[^>]*>Autobahn<\/a>/);
  assert.match(
    html,
    /<a href="https:\/\/hitchwiki\.org\/en\/Berlin_Tempelhof_Airport"[^>]*>Tempelhof<\/a>/,
  );
});

test("templates, images and refs are stripped, not leaked as prose", () => {
  const { renderExcerpt } = load();
  const html = renderExcerpt(
    "Intro text. {{Infobox|foo=bar}} [[File:berlin.jpg|thumb|A street]] More text.<ref>some citation</ref> End.",
  );
  assert.ok(!html.includes("Infobox"));
  assert.ok(!html.includes("berlin.jpg"));
  assert.ok(!html.includes("citation"));
  assert.match(html, /Intro text\./);
  assert.match(html, /More text\./);
  assert.match(html, /End\./);
});

test("headings become h4, bold/italic become strong/em", () => {
  const { renderExcerpt } = load();
  const html = renderExcerpt("== Getting there ==\n\nTake the '''A10''' or ''hitch'' from the exit.");
  assert.match(html, /<h4>Getting there<\/h4>/);
  assert.match(html, /<strong>A10<\/strong>/);
  assert.match(html, /<em>hitch<\/em>/);
});

test("HTML-significant characters in prose are escaped, not injected", () => {
  const { renderExcerpt } = load();
  const html = renderExcerpt('Drivers say "go fast" & <watch> the road.');
  assert.ok(!html.includes("<watch>"));
  assert.match(html, /&quot;go fast&quot;/);
  assert.match(html, /&amp;/);
});

test("{{FULLPAGENAME}} and friends resolve to the real title, not an empty subject", () => {
  // Regression test: Hitchwiki's real Berlin article opens with
  // "'''{{FULLPAGENAME}}''' is the capital of Germany" -- confirmed live
  // 2026-08-24. Blindly stripping {{...}} templates (needed for infoboxes)
  // would otherwise delete "Berlin" and leave orphaned bold markers.
  const { renderExcerpt } = load();
  const html = renderExcerpt("'''{{FULLPAGENAME}}''' is the capital of Germany.", "Berlin");
  assert.strictEqual(html, "<p><strong>Berlin</strong> is the capital of Germany.</p>");
});

test("a stray <br> becomes a line break, not a literal &lt;br&gt; paragraph", () => {
  // Regression test: Hitchwiki's real Berlin article opens with
  // "{{Coords-missing}}<br>\n{{infobox ...}}" -- confirmed live 2026-08-24.
  // The raw <br> used to survive into the escape step and print as its own
  // "<p>&lt;br&gt;</p>" paragraph.
  const { renderExcerpt } = load();
  const html = renderExcerpt("{{Coords-missing}}<br>\n{{infobox|x=y}}\n\nReal prose here.");
  assert.ok(!html.includes("br&gt;"), "raw <br> leaked through as text: " + html);
  assert.strictEqual(html, "<p>Real prose here.</p>");
});

test("other stray HTML tags are dropped, their text content kept", () => {
  const { renderExcerpt } = load();
  const html = renderExcerpt("Some <small>fine print</small> and <sup>a note</sup> here.");
  assert.strictEqual(html, "<p>Some fine print and a note here.</p>");
});

test("wikiLink turns a title into an absolute, space-safe article URL", () => {
  const { wikiLink } = load();
  assert.strictEqual(wikiLink("Sao Paulo"), "https://hitchwiki.org/en/Sao_Paulo");
});

test("an article with only templates/images and no prose renders to nothing", () => {
  const { renderExcerpt } = load();
  const html = renderExcerpt("{{Infobox|x=y}}\n\n[[File:only.jpg|thumb]]");
  assert.strictEqual(html, "");
});
