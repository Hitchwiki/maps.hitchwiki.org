// EXP-1334 / route-demand: journey_started carries the route-none-road and route-demand arms.
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");
const src = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "inride.js"), "utf8");

test("journey_started carries rnr and rd", () => {
  const ev = src.slice(src.indexOf('hmTrack("journey_started", {'));
  const body = ev.slice(0, ev.indexOf("});"));
  assert.ok(body.includes('rnr: storedArm("hm_ab_route-none-road-v1")'));
  assert.ok(body.includes('rd: storedArm("hmRouteDemandArm")'));
});

test("storedArm reads without assigning", () => {
  const start = src.indexOf("function storedArm(key)");
  const fnSrc = src.slice(start, src.indexOf("\n  }\n", start) + 4);
  const store = { hmRouteDemandArm: "show" };
  global.localStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: () => { throw new Error("assigned"); } };
  const storedArm = new Function(fnSrc + "; return storedArm;")();
  assert.strictEqual(storedArm("hmRouteDemandArm"), "show");
  assert.strictEqual(storedArm("hm_ab_route-none-road-v1"), "na");
  global.localStorage = { getItem: () => { throw new Error("blocked"); } };
  assert.strictEqual(storedArm("x"), "na");
  delete global.localStorage;
});
