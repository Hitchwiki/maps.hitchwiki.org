const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const src = fs.readFileSync(__dirname + "/../hitch/static/inride.js", "utf8");

test("picker requestFix publishes the fix to window.hmDeviceLatLng (dist bucket)", () => {
  const i = src.indexOf("function requestFix()");
  assert.ok(i > 0);
  const body = src.slice(i, i + 900);
  assert.match(body, /window\.hmDeviceLatLng = window\.hmDeviceLatLng \|\| \{ lat: fix\.lat, lon: fix\.lon \}/);
});
