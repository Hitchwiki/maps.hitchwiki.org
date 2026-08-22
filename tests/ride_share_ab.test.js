const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const SOURCE = fs.readFileSync(
  path.join(__dirname, "..", "hitch", "static", "map.js"),
  "utf8",
);

test("share value test has a sticky control and treatment", () => {
  assert.match(
    SOURCE,
    /chooseVariant\("ride-share-value-v1", \["control", "help-friend"\]\)/,
  );
  assert.match(SOURCE, /hmTrack\("ride_share_exposure", \{ variant: shareVariant \}\)/);
  assert.match(SOURCE, /Help a friend try hitchhiking/);
  assert.match(SOURCE, /Share a real ride and show them where hitchhiking worked for you\./);
});

test("every share outcome carries the assigned variant", () => {
  assert.match(
    SOURCE,
    /hmTrack\("ride_share", Object\.assign\(\{ variant: shareVariant \}, properties\)\)/,
  );
  assert.doesNotMatch(SOURCE, /hmTrack\("ride_share", \{/);
  for (const action of ["dismiss", "clicked", "shared"]) {
    assert.ok(SOURCE.includes(`action: "${action}"`), `missing ${action} outcome`);
  }
  for (const event of [
    "ride_share_clicked",
    "ride_share_shared",
    "ride_share_dismissed",
  ]) {
    assert.ok(SOURCE.includes(`"${event}"`), `missing aggregate ${event} event`);
  }
});
