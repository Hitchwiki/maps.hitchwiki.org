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
// EXP-1346 slice B: sticky iOS arm; the after_use arm waits for hm:useful, which base.html's hmTrack fires.
const base = fs.readFileSync(path.join(root, "templates", "base.html"), "utf8");
assert.ok(html.includes("hmVariant('ios-hint-moment-v1', ['ctrl', 'after_use'])"), "ios arm assigned");
assert.ok(/arm: iosArm/.test(html), "arm tagged on hint events");
assert.ok(html.includes("addEventListener('hm:useful', start, { once: true })"), "after_use waits for hm:useful");
assert.ok(base.includes("dispatchEvent(new Event('hm:useful'))"), "hmTrack fires hm:useful");
console.log("ok slice B");
