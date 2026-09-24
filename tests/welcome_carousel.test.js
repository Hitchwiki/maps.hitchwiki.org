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

test("open({onDone}) tears down and calls back instead of navigating to the profile form (#495)", () => {
  assert.match(SOURCE, /function open\(opts\)/);
  assert.match(SOURCE, /if \(!onDone\) return finish\(\);\s+teardown\(\);\s+_open = null;\s+onDone\(\);/);
  // Every exit path (skip, last-slide button, Escape) goes through done(), never finish() directly.
  assert.doesNotMatch(SOURCE, /addEventListener\("click", finish\)/);
  assert.doesNotMatch(SOURCE, /Escape"\) finish\(\)/);
  assert.match(SOURCE, /window\.location\.href = PROFILE_URL/);
});
