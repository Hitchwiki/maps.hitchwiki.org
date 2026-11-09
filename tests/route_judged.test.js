const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const source = fs.readFileSync(
  path.join(__dirname, "..", "hitch", "static", "routing.js"), "utf8"
);

test("route sheet has one judgement prompt: the thumbs vote, which also fires route_judged", () => {
  assert.doesNotMatch(source, /data-judge=/);
  assert.doesNotMatch(source, /rp-judge"/);
  assert.match(source, /Is this a good hitchhiking route\?/);
  assert.match(source, /hmTrack\("route_judged", \{ answer: vote === "up" \? "yes" : "no"/);
});

test("judgement logs the first answer only, with coarse 0.5 degree cells", () => {
  assert.match(source, /if \(vote\) return/);
  assert.match(source, /prior: prior, intent:/);
  assert.match(source, /hm_journeys_started/);
  assert.match(source, /Math\.round\(ll\[0\] \* 2\) \/ 2/);
});

test("route demand label is an A/B on corridors with >=20 requests (#1254)", () => {
  assert.match(source, /route_demand\.json/);
  assert.match(source, /hit\.requests < 20/);
  assert.match(source, /hmRouteDemandArm/);
  assert.match(source, /hmTrack\("route_demand_label"/);
});
