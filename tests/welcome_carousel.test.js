const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");

const SOURCE = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "welcome.js"), "utf8");

test("the first-run carousel states who stops as a plain aggregate, sourced", () => {
  // Publishing a number computed from our own logged rides, not authored advice.
  assert.match(SOURCE, /about one in four drivers who stopped was a woman/);
  assert.match(SOURCE, /research\/driver-gender-2026-08-31\.md/);
});

test("each carousel slide reports itself once so the surface is measurable", () => {
  assert.match(SOURCE, /window\.hmTrack\("welcome_slide_shown", \{ slide: i \}\)/);
  // Dedup guard: render() runs on every scroll settle.
  assert.match(SOURCE, /if \(slideSeen\[i\]\) return;/);
  assert.match(SOURCE, /trackSlide\(i\);/);
});

test("the who-pulls-over slide links the safety page with a ?ref= tag (#581)", () => {
  // Points at guaka's cohort-filterable safety page rather than restating a number here;
  // the query param lets pageviews from this slide be told apart from the map menu link.
  assert.match(SOURCE, /href: "\/hitchhiking-safety\?ref=welcome-carousel"/);
  assert.match(SOURCE, /window\.hmTrack\("welcome_link_click", \{ href: s\.link\.href \}\)/);
});

test("open({onDone}) tears down and calls back instead of navigating to the profile form (#495)", () => {
  assert.match(SOURCE, /function open\(opts\)/);
  assert.match(SOURCE, /if \(!onDone\) return finish\(\);\s+teardown\(\);\s+_open = null;\s+onDone\(\);/);
  // Every exit path (skip, last-slide button, Escape) goes through done(), never finish() directly.
  assert.doesNotMatch(SOURCE, /addEventListener\("click", finish\)/);
  assert.doesNotMatch(SOURCE, /Escape"\) finish\(\)/);
  assert.match(SOURCE, /window\.location\.href = PROFILE_URL/);
});

test("anonymous first-visit A/B (#268): both arms assigned at show time, four funnel events tagged", () => {
  assert.match(SOURCE, /hmVariant\(ANON_EXP, \["control", "welcome"\]\)/);
  assert.match(SOURCE, /ANON_EXP = "welcome-anon-v1"/);
  assert.match(SOURCE, /welcome_anon_assigned/);
  for (const ev of ["spot_opened", "route_searched", "journey_started", "add_ride_clicked"]) {
    assert.match(SOURCE, new RegExp(ev + ": 1"));
  }
  // Logged-in users, ?welcome=1 and friend-share landings are excluded; modals are never stacked on.
  assert.match(SOURCE, /window\.IS_LOGGED_IN !== false/);
  assert.match(SOURCE, /\^share-/);
  assert.match(SOURCE, /\.inride-scrim/);
  // Anonymous finishers stay on the map, not the login-gated profile form.
  assert.match(SOURCE, /onDone: function \(\) \{\}/);
});
