const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const JS = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "map.js"), "utf8");
const HTML = fs.readFileSync(path.join(__dirname, "..", "hitch", "templates", "map.html"), "utf8");

// #254: the success overlay used to link out to a Google Form (0 responses ever).
// It now carries an inline free-text field whose answer rides an analytics event.

test("the dead Google Form link is gone from the success overlay", () => {
  assert.doesNotMatch(HTML, /success-feedback-link/);
  assert.doesNotMatch(JS, /feedback_link_clicked.*success-overlay/);
});

test("the overlay markup has the inline feedback field", () => {
  assert.match(HTML, /id="map-feedback"[\s\S]*data-source="success-overlay"/);
  assert.match(HTML, /id="map-feedback-text"[\s\S]*maxlength="500"/);
  assert.match(HTML, /id="map-feedback-toggle"/);
  assert.match(HTML, /id="map-feedback-send"/);
});

test("setupMapFeedback tracks open and submit, caps the note, and is called per overlay open", () => {
  assert.match(JS, /function setupMapFeedback\(source\)/);
  assert.match(JS, /hmTrack\("map_feedback_opened", \{ source: source \}\)/);
  assert.match(JS, /hmTrack\("map_feedback_submitted", \{ source: source, chars: note\.length, text: note \}\)/);
  assert.match(JS, /text\.value\.trim\(\)\.slice\(0, 500\)/);
  assert.match(JS, /setupMapFeedback\("success-overlay"\)/);
});

test("the widget resets its state each time it is set up", () => {
  const body = JS.slice(JS.indexOf("function setupMapFeedback"), JS.indexOf("function showSuccessOverlay"));
  assert.match(body, /text\.value = "";/);
  assert.match(body, /thanks\.hidden = true;/);
  assert.match(body, /if \(!root\) return;/);
});
