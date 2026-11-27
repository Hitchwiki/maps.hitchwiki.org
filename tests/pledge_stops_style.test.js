const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const src = fs.readFileSync(__dirname + "/../hitch/static/map.js", "utf8");
test("pledge stops link has a sticky link/button style arm and reports it", () => {
  assert.match(src, /"pledge-stops-style-v1", \["link", "button"\]/);
  assert.match(src, /driver_pledge_stops_link_clicked", \{ surface: surface, arm: arm, style: styleArm \}/);
});
