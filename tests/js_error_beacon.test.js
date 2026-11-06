// IDEAS #1291: the error beacon in base.html is bounded, scrubbed and bucketed.
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const html = fs.readFileSync(path.join(__dirname, "../hitch/templates/base.html"), "utf8");
const block = html.slice(html.indexOf("#1291: front-end error beacon"));
const iife = block.slice(block.indexOf("(function () {"), block.indexOf("})();") + 5);

function run(events, origin) {
  const handlers = {}, tracked = [];
  const window = {
    hmTrack: (n, d) => tracked.push([n, d]),
    addEventListener: (t, f) => (handlers[t] = f),
  };
  new Function("window", "location", iife)(window, { origin });
  for (const e of events) handlers[e.type](e);
  return tracked;
}
const O = "https://maps.hitchwiki.org";

test("own file error is bucketed and message scrubbed", () => {
  const t = run([{ type: "error", filename: O + "/static/map.js?v=1", lineno: 7, message: "x https://a.b/c 12345 y", error: { name: "TypeError" } }], O);
  assert.deepStrictEqual(t, [["js_error", { f: "map", l: 7, n: "TypeError", m: "x URL N y" }]]);
});
test("duplicates are dropped and the cap is 3", () => {
  const ev = (l) => ({ type: "error", filename: O + "/static/map.js", lineno: l, message: "m", error: { name: "E" } });
  assert.strictEqual(run([ev(1), ev(1), ev(2), ev(3), ev(4)], O).length, 3);
});
test("foreign file sends no message", () => {
  const t = run([{ type: "error", filename: "https://evil.example/x.js", lineno: 1, message: "secret", error: { name: "E" } }], O);
  assert.strictEqual(t[0][1].f, "ext");
  assert.ok(!("m" in t[0][1]));
});
test("unhandled rejection reports as rej", () => {
  const t = run([{ type: "unhandledrejection", reason: { name: "NetworkError", message: "fail" } }], O);
  assert.strictEqual(t[0][1].f, "rej");
});
test("rejection reasons never send a message", () => {
  const t = run([{ type: "unhandledrejection", reason: { name: "E", message: "user typed secret" } }], O);
  assert.ok(!("m" in t[0][1]));
});
