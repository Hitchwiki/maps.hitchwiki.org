const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const SRC = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "inride.js"), "utf8");

test("#795: the login stash carries a timestamp", () => {
  assert.match(SRC, /source: source, at: Date\.now\(\)/);
});
test("#795: returning logged out records an event and re-offers the anonymous start", () => {
  assert.match(SRC, /hmTrack\("journey_login_return"/);
  assert.match(SRC, /hmTrack\("journey_login_return_outcome", \{ outcome: "anonymous" \}\)/);
  assert.match(SRC, /2 \* 3600 \* 1000/);
});
test("#795: the return branch no longer short-circuits the rest of initInride", () => {
  const i = SRC.indexOf('hmTrack("journey_login_return"');
  const j = SRC.indexOf("loadDemographicData();", i);
  assert.ok(j > i);
  assert.doesNotMatch(SRC.slice(i, j), /\n\s+return;\n/);
});
