const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const inrideSource = fs.readFileSync(
  path.join(__dirname, "..", "hitch", "static", "inride.js"), "utf8"
);
const submitSource = fs.readFileSync(
  path.join(__dirname, "..", "hitch", "static", "ride_submit.js"), "utf8"
);

test("give-up sheet's Save button is never disabled on the star rating (#438 slice 2)", () => {
  const giveUpFn = inrideSource.slice(
    inrideSource.indexOf("giveUpSheet(onSave) {"),
    inrideSource.indexOf("close() {", inrideSource.indexOf("giveUpSheet(onSave) {"))
  );
  assert.doesNotMatch(giveUpFn, /updateSaveBtn/);
  assert.doesNotMatch(giveUpFn, /saveBtn\.disabled/);
  assert.doesNotMatch(giveUpFn, /saveBtn\.classList\.(add|toggle)\(["']inr-disabled["']/);
});

test("give-up sheet offers the two existing-wording reason chips", () => {
  assert.match(inrideSource, /code: "no_traffic", label: "🚗 " \+ T\("No traffic"\)/);
  assert.match(inrideSource, /code: "bad_pull_in_spot", label: "🅿️ " \+ T\("Bad pull-in spot"\)/);
});

test("give-up sheet tracks reason selection and passes reasons to onSave", () => {
  assert.match(inrideSource, /hmTrack\("giveup_reason_selected", \{ reason: opt\.code \}\)/);
  assert.match(inrideSource, /onSave\(\{ rating: rating, reasons: Array\.from\(reasons\), comment: textarea\.value\.trim\(\) \}\)/);
});

test("give-up sheet still tracks shown/dismissed unchanged", () => {
  assert.match(inrideSource, /hmTrack\("giveup_sheet_shown", \{\}\)/);
  assert.match(inrideSource, /hmTrack\("giveup_sheet_dismissed", \{\}\)/);
});

test("buildGiveUpBody folds reasons into the comment since /ride has no reason column", () => {
  assert.match(submitSource, /no_traffic: "no traffic", bad_pull_in_spot: "bad pull-in spot"/);
  assert.match(submitSource, /details\.reasons \|\| \[\]/);
});

test("buildGiveUpBody with no reasons behaves exactly as before", () => {
  const { buildGiveUpBody } = require("../hitch/static/ride_submit.js");
  const j = { pickup: { lat: 1, lon: 2 }, coHitchhikers: [] };
  const body = buildGiveUpBody(j, 12, { rating: 3, comment: "quiet spot" }, "abc123");
  assert.strictEqual(body.comment, "quiet spot");
  assert.strictEqual(body.rate, "3");
  assert.strictEqual(body.no_ride, "1");
});

test("buildGiveUpBody prefixes the comment with selected reason labels", () => {
  const { buildGiveUpBody } = require("../hitch/static/ride_submit.js");
  const j = { pickup: { lat: 1, lon: 2 }, coHitchhikers: [] };
  const body = buildGiveUpBody(j, 12, { rating: 0, reasons: ["no_traffic", "bad_pull_in_spot"], comment: "" }, "abc123");
  assert.strictEqual(body.comment, "[no traffic, bad pull-in spot]");
});
