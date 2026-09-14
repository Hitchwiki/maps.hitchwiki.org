// The share card's permalink must carry ?ref=ride-share so base.html's
// referred_via capture (#144, tests/ref_attribution.test.js) can count the
// people who follow a shared ride back to the map. share_card.js builds its
// URL inside a canvas.toBlob callback that can't be require()d in isolation,
// so this asserts against the source, the same way ride_share_ab.test.js does
// for map.js.

const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const SOURCE = fs.readFileSync(
  path.join(__dirname, "..", "hitch", "static", "share_card.js"),
  "utf8",
);

test("both the ride and spot permalink fall-through carry ?ref=ride-share", () => {
  // one shared suffix on the (ride ? .../ride/ : .../spot/) expression, so the
  // fallback spot link is tagged too — not just the happy-path ride link.
  assert.match(
    SOURCE,
    /"\/spot\/" \+ spotId\)\s*\+\s*"\?ref=ride-share"/,
  );
  assert.doesNotMatch(SOURCE, /\/ride\/" \+ encodeURIComponent\(dTag\);/);
});

test("the ref tag matches base.html's sanitiser (alphanumeric + dash only)", () => {
  const m = SOURCE.match(/"\?ref=([^"]+)"/);
  assert.ok(m, "no ?ref= literal found in share_card.js");
  assert.strictEqual(m[1], m[1].replace(/[^a-zA-Z0-9_-]/g, ""));
  assert.ok(m[1].length <= 64);
});
