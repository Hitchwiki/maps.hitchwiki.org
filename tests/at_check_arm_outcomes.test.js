// EXP-1200: end events carry the at-spot-check arm so rides-per-start can be split by arm.
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");
const src = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "inride.js"), "utf8");

test("journey state records the at-check arm before the label is cleared", () => {
  const set = src.indexOf('atCheck: atCheckLabel || "na"');
  const clear = src.indexOf('atCheckLabel = ""; // one-shot');
  assert.ok(set > 0 && clear > set);
});

test("cohortProps carries the arm as ac", () => {
  assert.ok(src.includes('ac: j && j.atCheck ? j.atCheck : "na"'));
});
