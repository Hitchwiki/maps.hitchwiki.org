const test = require("node:test");
const assert = require("node:assert");
const src = require("fs").readFileSync(__dirname + "/../hitch/static/routing.js", "utf8");
const m = src.match(/const VEHICLE_CODES = (\{[^}]*\});\n\s*\/\/[^\n]*\n\s*(function crossBorderCode[\s\S]*?\n  \})/);
const { VEHICLE_CODES, crossBorderCode } = new Function(`const VEHICLE_CODES = ${m[1]}; ${m[2]}; return { VEHICLE_CODES, crossBorderCode };`)();

test("vehicle code table", () => {
  assert.strictEqual(VEHICLE_CODES.DE, "D");
  assert.strictEqual(VEHICLE_CODES.CZ, "CZ");
  assert.strictEqual(VEHICLE_CODES.SI, "SLO");
});
test("only cross-border destinations get a code", () => {
  assert.strictEqual(crossBorderCode("cz", "DE"), "CZ");
  assert.strictEqual(crossBorderCode("DE", "DE"), null);
  assert.strictEqual(crossBorderCode(null, "DE"), null);
  assert.strictEqual(crossBorderCode("JP", "DE"), null);
});
test("sign_country event is tracked", () => {
  assert.match(src, /hmTrack\("sign_country"/);
});
