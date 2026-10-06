const test = require("node:test");
const assert = require("node:assert");
const src = require("fs").readFileSync(__dirname + "/../hitch/static/routing.js", "utf8");

test("sign screen leads with the destination's local-script name", () => {
  assert.match(src, /function localSignName\(name\)/);
  assert.match(src, /lang=default&layer=city&radius=30/);
  assert.match(src, /p\.osm_value === "city"/);
  assert.match(src, /hmTrack\("sign_local_name", \{ source \}\)/);
  assert.match(src, /n\.trim\(\)\.toLowerCase\(\) !== name\.trim\(\)\.toLowerCase\(\) \? n\.trim\(\) : null/);
});
