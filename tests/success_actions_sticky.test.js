const fs = require("fs");
const assert = require("assert");
const css = fs.readFileSync(__dirname + "/../hitch/static/style.css", "utf8");
const m = css.match(/\.success-share-content \.signup-prompt-actions\s*\{[^}]*\}/);
assert(m, "sticky rule for the ride-saved card actions exists (#893)");
assert(/position:\s*sticky/.test(m[0]) && /bottom:/.test(m[0]), "actions are pinned to the bottom of the scrolling card");
console.log("ok success_actions_sticky");
