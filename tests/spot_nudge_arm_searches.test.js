// EXP-1672: route_searched carries the spot-plan-nudge arm of an eligible session.
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");
const read = (f) => fs.readFileSync(path.join(__dirname, "..", "hitch", "static", f), "utf8");

test("eligibility stores the arm, not a bare flag", () => {
  assert.ok(read("map.js").includes('sessionStorage.setItem("hm_spot_plan_nudge_elig", arm)'));
});

test("route_searched carries spn", () => {
  const src = read("routing.js");
  assert.ok(src.includes("sessionStorage.getItem('hm_spot_plan_nudge_elig') || 'na'"));
  assert.ok(/hmTrack\('route_searched', \{[^}]*spn: spn[,} ]/.test(src));
});
