const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "../hitch/static/routing.js"), "utf8");

test("route rows get a Make a sign button wired to openSign", () => {
  assert.match(src, /class="rp-sign-btn"[^>]*>\$\{T\("Make a sign"\)\}/);
  assert.match(src, /rp-sign-btn"\)\.addEventListener\("click", \(\) => openSign\("route", i\)\)/);
});

test("sign tracks open, invert and print", () => {
  for (const ev of ["sign_opened", "sign_inverted", "sign_printed"]) {
    assert.ok(src.includes(`hmTrack("${ev}"`), ev);
  }
});

test("sign uses only the town part of the destination label", () => {
  assert.match(src, /label\.split\(","\)\[0\]\.trim\(\)/);
});
