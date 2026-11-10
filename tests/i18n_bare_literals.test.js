// IDEAS #1359: ~80% of maps pageviews are on localized prefixes, but visitor-facing strings
// kept shipping as bare English literals and getting fixed afterwards (maps#565, #567, #590).
// This fails when a static script assigns a multi-word English literal straight to
// textContent / innerText / title / placeholder instead of going through tr() / T().
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const FILES = ["map.js", "inride.js", "routing.js", "account.js"];
// Deliberately English. Test-mode chrome is internal. The planner links stay English while the
// #1336/#1210 link experiments are measured (tests/success_plan_link.test.js pins one of them), and
// the insights outlier note is an analyst caption. Add a string here only with a reason.
const ALLOW = new Set([
  "Exit test mode",
  "See what the route planner suggests for this trip",
  "Experimental: try the new route planner for this trip",
  "Experimental: compare with the new route planner",
]);
const ALLOW_PREFIX = ["Hiding ${hidden"];
// .prop = "Two words..." (an optional emoji/symbol prefix is fine; the words are what matter).
const BARE = /\.(?:textContent|innerText|title|placeholder)\s*=\s*(["'`])([^"'`]*[A-Za-z][A-Za-z']*\s+[A-Za-z][^"'`]*)\1\s*;/;

test("no bare multi-word English literals in visitor-facing assignments", () => {
  const hits = [];
  for (const f of FILES) {
    const src = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", f), "utf8");
    src.split("\n").forEach((line, i) => {
      const m = line.match(BARE);
      if (m && !ALLOW.has(m[2].trim()) && !ALLOW_PREFIX.some((p) => m[2].startsWith(p))) hits.push(`${f}:${i + 1}: ${m[2]}`);
    });
  }
  assert.deepStrictEqual(hits, [], "wrap these in tr()/T() and add the key to hitch/translations/*.json");
});

test("the guard still catches a bare literal (self-check)", () => {
  assert.ok(BARE.test('btn.textContent = "🚗 I\'m driving";'));
  assert.ok(!BARE.test('btn.textContent = "🚗 " + T("I\'m driving");'));
  assert.ok(!BARE.test('el.textContent = T("No spots found");'));
});
