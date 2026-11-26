// EXP-1405/1409: routing_opened and route_searched carry the planner A/B arms (ml, rc).
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");
const src = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "routing.js"), "utf8");

test("both events carry plannerArms()", () => {
  assert.ok(src.includes("hmTrack('routing_opened', plannerArms());"));
  assert.ok(/hmTrack\('route_searched', \{[^}]*\.\.\.plannerArms\(\) \}\)/.test(src));
});

test("plannerArms reads stored arms without assigning one", () => {
  const body = src.slice(src.indexOf("function plannerArms()"), src.indexOf("// ---- open / close"));
  assert.ok(!body.includes("hmVariant"));
  const store = { "hm_ab_myloc-start-v1": "on" };
  global.localStorage = { getItem: (k) => (k in store ? store[k] : null) };
  const fn = new Function(body + "; return plannerArms();");
  assert.deepStrictEqual(fn(), { ml: "on", rc: "na" });
  global.localStorage = { getItem: () => { throw new Error("blocked"); } };
  assert.deepStrictEqual(fn(), { ml: "na", rc: "na" });
  delete global.localStorage;
});
