"use strict";

// The "As GPX (to import into offline maps)" menu link downloads the whole-world
// /spots.gpx (~33 MB, all spots with names + waits). The per-country picker next
// to it already fires `country_gpx_downloaded`, but the world link fired nothing,
// so we could not tell how many people take the offline export. country_gpx.js
// now wires an id'd anchor to a `world_gpx_downloaded` Umami event.

const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const SOURCE = fs.readFileSync(
  path.join(__dirname, "..", "hitch", "static", "country_gpx.js"),
  "utf8",
);
const TEMPLATE = fs.readFileSync(
  path.join(__dirname, "..", "hitch", "templates", "map.html"),
  "utf8",
);

test("the world GPX menu link carries the id the tracker binds to", () => {
  assert.match(
    TEMPLATE,
    /<a id="world-gpx-download" href="\/spots\.gpx" download>/,
    "map.html no longer gives the /spots.gpx link the world-gpx-download id",
  );
});

test("country_gpx.js fires world_gpx_downloaded on that link", () => {
  assert.match(SOURCE, /getElementById\("world-gpx-download"\)/);
  assert.match(SOURCE, /hmTrack\("world_gpx_downloaded"\)/);
});

test("wireWorldGpx is called from init and guards against double-binding", () => {
  assert.match(SOURCE, /async function init\(\)\s*\{\s*wireWorldGpx\(\);/);
  assert.match(SOURCE, /worldLink\.dataset\.hmWired/);
});
