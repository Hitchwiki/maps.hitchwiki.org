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
// #1724: after-save shows are tagged as their own arm so they stay out of ctrl/after_use.
assert.ok(/arm: source === 'after_save' \? 'after_save' : iosArm/.test(html), "arm tagged on hint events");
assert.ok(html.includes("addEventListener('hm:useful', start, { once: true })"), "after_use waits for hm:useful");
assert.ok(base.includes("dispatchEvent(new Event('hm:useful'))"), "hmTrack fires hm:useful");
console.log("ok slice B");
// IDEAS #1724: the success screen's close fires hm:ride_saved_closed and the hint listens for it.
assert.ok(js.includes('dispatchEvent(new CustomEvent("hm:ride_saved_closed"))'), "success close fires hm:ride_saved_closed");
assert.ok(html.includes("addEventListener('hm:ride_saved_closed'"), "install hint offers after a save");
assert.ok(html.includes("'installAfterSaveShownAt'"), "after-save offer has its own 30-day key");
console.log("ok #1724");
