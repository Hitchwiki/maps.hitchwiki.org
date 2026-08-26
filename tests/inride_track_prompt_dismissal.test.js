const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const SOURCE = fs.readFileSync(
  path.join(__dirname, "..", "hitch", "static", "inride.js"),
  "utf8",
);

// Real bug found while diagnosing the 903 journey_start_button_clicked -> 264
// journey_started drop: for an anonymous hitchhiker, confirming the waiting-spot pin
// doesn't start the journey -- it opens a second "Track your rides?" dialog first. A
// scrim tap on THAT dialog used to lose the whole journey silently (no event, no
// journey, the placed pin just gone), on top of never being instrumented at all.

test("dialog() tells onClose why it closed, not just that it closed", () => {
  // close() must accept a reason and pass it through -- onClose cannot infer the
  // reason from execution order, since close() always runs before the clicked
  // button's own onClick (see the comment in dialog()).
  assert.match(SOURCE, /function close\(reason\)/);
  assert.match(SOURCE, /if \(onClose\) onClose\(reason\)/);
});

test("dialog()'s own close() call sites pass a real reason, never a raw DOM event", () => {
  // A bare `scrim.addEventListener("click", close)` (or the cancel-x button's
  // equivalent) would hand the MouseEvent to close() as `reason`. Scoped to the
  // dialog() function's own body: rideDetailsSheet has its own unrelated local
  // `close` with no reason parameter, and a bare `scrim.addEventListener("click",
  // close)` there is fine -- it isn't the one onClose(reason) callers rely on.
  const dialogFnStart = SOURCE.indexOf("dialog({ title, body, actions, onClose, centered, forced, cancelButton }) {");
  assert.ok(dialogFnStart > -1, "could not locate dialog()'s definition");
  const dialogFnBody = SOURCE.slice(dialogFnStart, dialogFnStart + 4000);
  assert.match(dialogFnBody, /close\("button"\)/);
  assert.match(dialogFnBody, /close\("cancel-x"\)/);
  assert.match(dialogFnBody, /close\("scrim"\)/);
  assert.doesNotMatch(dialogFnBody, /scrim\.addEventListener\("click",\s*close\)/);
  assert.doesNotMatch(dialogFnBody, /cancelBtn\.addEventListener\("click",\s*close\)/);
});

test("the track-rides prompt sends a shown event with source", () => {
  assert.match(SOURCE, /hmTrack\("journey_track_prompt_shown", \{ source: source \}\)/);
});

test("both explicit choices are tracked before they act", () => {
  assert.match(
    SOURCE,
    /hmTrack\("journey_track_prompt_outcome", \{ outcome: "login" \}\);[\s\S]{0,400}window\.location\.href = "\/login\?next=\/";/,
  );
  assert.match(
    SOURCE,
    /hmTrack\("journey_track_prompt_outcome", \{ outcome: "anonymous" \}\);\s*journeyFlow\.beginWithCoHitchers\(p, source\);/,
  );
});

test("a scrim/cancel-x dismissal directly starts anonymously, tracked as dismissed", () => {
  assert.match(
    SOURCE,
    /onClose: \(reason\) => \{[\s\S]{0,900}if \(reason !== "scrim" && reason !== "cancel-x"\) return;[\s\S]{0,900}hmTrack\("journey_track_prompt_outcome", \{ outcome: "dismissed" \}\);[\s\S]{0,900}journeyFlow\.start\(p, \[\], source\);[\s\S]{0,100}\}/,
  );
  // Opening the optional co-hitchhiker sheet here recreates the measured second
  // gate: dismissing that sheet aborts the start. Only the explicit anonymous
  // choice should retain the companion-selection step.
  const dismissBranch = SOURCE.slice(
    SOURCE.indexOf("onClose: (reason) => {", SOURCE.indexOf("journey_track_prompt_shown")),
    SOURCE.indexOf("    });", SOURCE.indexOf("onClose: (reason) => {", SOURCE.indexOf("journey_track_prompt_shown"))),
  );
  assert.doesNotMatch(dismissBranch, /beginWithCoHitchers/);
});

test("a dialog forced closed by another dialog opening does not auto-start a journey", () => {
  // journeyUI._openDialog.close() (the "one dialog at a time" guard, used at every
  // call site in the file) must call close() with no argument -- onClose(undefined)
  // then correctly fails the reason === "scrim" / "cancel-x" check above, so opening
  // any other dialog while this one is up cannot silently start a journey the
  // hitchhiker never asked for.
  const closeCalls = SOURCE.match(/journeyUI\._openDialog\.close\([^)]*\)/g) || [];
  assert.ok(closeCalls.length > 0, "expected at least one _openDialog.close() call site");
  for (const call of closeCalls) {
    assert.match(call, /journeyUI\._openDialog\.close\(\)/, `${call} must pass no reason`);
  }
});
