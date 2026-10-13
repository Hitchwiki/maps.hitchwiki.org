const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");

const SOURCE = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "map.js"), "utf8");

test("map-mode switches are counted once, user-initiated only (#813)", () => {
  assert.match(SOURCE, /async function setMapMode\(mode\) \{[^}]*if \(mode !== mapMode\) hmTrack\("map_mode_switched", \{ mode: String\(mode\) \}\);/);
});

test("hitchhiker marker opens carry no name or place (#813)", () => {
  assert.match(SOURCE, /\.on\("popupopen", \(\) => hmTrack\("hitchhiker_marker_opened", \{\}\)\)/);
});

test("popup link clicks are told apart as profile vs hello (#813)", () => {
  assert.match(SOURCE, /closest\("\.hitchhiker-popup a"\)/);
  assert.match(SOURCE, /hmTrack\("hitchhiker_popup_click", \{ kind: /);
});
