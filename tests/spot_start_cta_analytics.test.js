const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const SOURCE = fs.readFileSync(
  path.join(__dirname, "..", "hitch", "static", "map.js"),
  "utf8",
);

test("spot start exposure is based on the button inside the scrolling sheet", () => {
  assert.match(SOURCE, /new IntersectionObserver/);
  assert.match(SOURCE, /root: sheetBody, threshold: \[0\.75\]/);
  assert.match(SOURCE, /entry\.target === hitchBtn[\s\S]*entry\.intersectionRatio >= 0\.75/);
  assert.match(SOURCE, /hmTrack\("spot_start_cta_viewed", \{ variant: spotCtaVariant \}\)/);
});

test("each spot open resets the observer and a click has a direct event", () => {
  assert.match(SOURCE, /spotStartCtaObserver\.disconnect\(\);\s*spotStartCtaObserver = null/);
  assert.match(SOURCE, /hitchBtn\.style\.display[\s\S]*observeSpotStartCta\(hitchBtn\)/);
  assert.match(SOURCE, /hitchBtn\.onclick[\s\S]*hmTrack\("spot_start_cta_clicked", \{ variant: spotCtaVariant \}\)/);
});

test("#515: both spot-CTA events carry the A/B variant; non-English is control-i18n", () => {
  assert.match(SOURCE, /hmTrack\("spot_start_cta_viewed", \{ variant: spotCtaVariant \}\)/);
  assert.match(SOURCE, /hmTrack\("spot_start_cta_clicked", \{ variant: spotCtaVariant \}\)/);
  assert.match(SOURCE, /"control-i18n"[\s\S]*"spot-start-cta-v1", \["control", "start-here"\]/);
  // must not go through chooseVariant, a const declared far below this code (TDZ)
  assert.doesNotMatch(SOURCE, /chooseVariant\("spot-start-cta-v1"/);
});
