// The route-sheet intent chips must override `.sidebar button` (width:100%, big margins) so they sit in one row.
const fs = require("fs"), assert = require("assert");
const css = fs.readFileSync(__dirname + "/../hitch/static/style.css", "utf8");
const m = css.match(/\.rp-intent-choices button \{([^}]*)\}/);
assert(m, "rule missing");
assert(/width:\s*auto/.test(m[1]) && /margin:\s*0/.test(m[1]));
console.log("intent_chips_row ok");
