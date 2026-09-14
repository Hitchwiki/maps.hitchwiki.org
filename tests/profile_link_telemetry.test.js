const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const BASE = fs.readFileSync(
  path.join(__dirname, "..", "hitch", "templates", "base.html"),
  "utf8",
);
const CARD = fs.readFileSync(
  path.join(__dirname, "..", "hitch", "templates", "_ride_card.html"),
  "utf8",
);
const MAPJS = fs.readFileSync(
  path.join(__dirname, "..", "hitch", "static", "map.js"),
  "utf8",
);

// #246 slice 2: the hitchhiker name is already a profile link everywhere it
// renders; this adds the click telemetry the social-layer audit found missing.

test("a hitchhiker name is a link to their profile, server-side and client-side", () => {
  assert.match(CARD, /<a class="hitchhiker-name" href="\/account\//);
  assert.match(MAPJS, /<a class="hitchhiker-name" href="\/account\//);
});

test("base.html fires one delegated profile_link_clicked event with a source", () => {
  assert.match(BASE, /a\.hitchhiker-name/);
  assert.match(BASE, /hmTrack\('profile_link_clicked', \{ source: source \}\)/);
});

test("the source distinguishes the spot pane and the leaderboard", () => {
  const block = BASE.slice(BASE.indexOf("profile_link_clicked") - 600, BASE.indexOf("profile_link_clicked") + 60);
  assert.match(block, /#spot-text.*\?\s*'spot-pane'/s);
  assert.match(block, /\.leaderboard-pane.*\?\s*'leaderboard'/s);
});

test("the handler no-ops when hmTrack is not present", () => {
  assert.match(BASE, /if \(!link \|\| !window\.hmTrack\) return;/);
});
