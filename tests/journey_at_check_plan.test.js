const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");
const SOURCE = fs.readFileSync(path.join(__dirname, "../hitch/static/inride.js"), "utf8");

test("at-spot dialog offers a planner hand-off only when RoutingUI.openFrom exists", () => {
  const i = SOURCE.indexOf("function atSpotCheck");
  assert.ok(i > 0);
  const body = SOURCE.slice(i, i + 2000);
  assert.match(body, /window\.RoutingUI && window\.RoutingUI\.openFrom/);
  assert.match(body, /T\("Plan a route from here"\)/);
  assert.match(body, /hmTrack\("journey_at_check_plan_clicked", \{ source: source \}\)/);
  assert.match(body, /openFrom\(\[p\.lat, p\.lon\], null\)/);
});
