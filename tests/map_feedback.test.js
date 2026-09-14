const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const JS = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "map.js"), "utf8");
const HTML = fs.readFileSync(path.join(__dirname, "..", "hitch", "templates", "map.html"), "utf8");
const MACRO = fs.readFileSync(
  path.join(__dirname, "..", "hitch", "templates", "_feedback_widget.html"),
  "utf8",
);

// #254: the map used to link out to a Google Form (0 responses ever). It now
// carries an inline free-text field, rendered by the feedback_widget() macro in
// several places, whose answer rides an analytics event AND POSTs to /log-feedback.

test("every dead Google Form link is gone", () => {
  assert.doesNotMatch(HTML, /docs\.google\.com\/forms/);
  assert.doesNotMatch(HTML, /success-feedback-link|signup-prompt-feedback-link/);
  assert.doesNotMatch(JS, /feedback_link_clicked/);
});

test("the macro is class-based, caps the note, and has an optional email field", () => {
  assert.match(MACRO, /\{% macro feedback_widget\(source, prompt, allow_email=false, dismissible=false\) %\}/);
  assert.match(MACRO, /class="map-feedback"[\s\S]*data-source="\{\{ source \}\}"/);
  assert.match(MACRO, /class="map-feedback-text"[\s\S]*maxlength="500"/);
  assert.match(MACRO, /\{% if allow_email %\}[\s\S]*type="email"[\s\S]*class="map-feedback-email"/);
  assert.match(MACRO, /\{% if dismissible %\}[\s\S]*map-feedback-dismiss/);
  assert.doesNotMatch(MACRO, /id="map-feedback/);
});

test("the widget is rendered in the three placements", () => {
  assert.match(HTML, /feedback_widget\("success-overlay",.*allow_email=\(not is_logged_in\)\)/);
  assert.match(HTML, /feedback_widget\("signup-prompt",.*allow_email=true\)/);
  assert.match(HTML, /id="ambient-feedback-wrap" hidden/);
  assert.match(HTML, /feedback_widget\("ambient",.*dismissible=true\)/);
});

test("setupMapFeedback wires one instance by root element and tracks open/submit", () => {
  assert.match(JS, /function setupMapFeedback\(root, source\)/);
  assert.match(JS, /root\.querySelector\("\.map-feedback-text"\)/);
  assert.match(JS, /hmTrack\("map_feedback_opened", \{ source: source \}\)/);
  assert.match(JS, /hmTrack\("map_feedback_submitted", \{ source: source, chars: note\.length, text: note, has_email: !!addr \}\)/);
  assert.match(JS, /text\.value\.trim\(\)\.slice\(0, 500\)/);
  assert.match(JS, /postMapFeedback\(source, note, addr\)/);
});

test("the note is posted to /log-feedback via sendBeacon", () => {
  const body = JS.slice(JS.indexOf("function postMapFeedback"), JS.indexOf("function maybeShowAmbientFeedback"));
  assert.match(body, /navigator\.sendBeacon\("\/log-feedback"/);
});

test("the widget resets its state each time it is set up", () => {
  const body = JS.slice(JS.indexOf("function setupMapFeedback"), JS.indexOf("function postMapFeedback"));
  assert.match(body, /text\.value = "";/);
  assert.match(body, /thanks\.hidden = true;/);
  assert.match(body, /if \(!root\) return;/);
});

test("the ambient popup is sampled, cooled down, and fired after a real action", () => {
  const body = JS.slice(
    JS.indexOf("function maybeShowAmbientFeedback"),
    JS.indexOf("function maybeShowAmbientFeedback") + 900,
  );
  assert.match(body, /Math\.random\(\) >= AMBIENT_FEEDBACK_CHANCE/);
  assert.match(body, /AMBIENT_FEEDBACK_COOLDOWN_MS/);
  assert.match(JS, /maybeShowAmbientFeedback\("spot-opened"\)/);
});
