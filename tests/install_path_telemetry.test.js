"use strict";
// IDEAS #1346 slice A: install-path telemetry events stay wired.
const assert = require("assert"), fs = require("fs"), path = require("path");
const root = path.join(__dirname, "..", "hitch");
const js = fs.readFileSync(path.join(root, "static", "map.js"), "utf8");
const html = fs.readFileSync(path.join(root, "templates", "map.html"), "utf8");
assert.ok(/display: standaloneDisplay \? "standalone" : "browser"/.test(js), "map_ready carries display");
assert.ok(html.includes("'install_hint_shown'"), "install_hint_shown fired");
assert.ok(html.includes("'install_hint_dismissed'"), "install_hint_dismissed fired");
console.log("ok");
