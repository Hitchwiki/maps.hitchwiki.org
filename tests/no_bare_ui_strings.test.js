// Guard: user-visible multi-word English literals must go through T()/tr().
// Catches `x.textContent|title|placeholder = "Capitalised word word"` not wrapped in a translation call.
const fs = require("fs");
const path = require("path");
const files = ["map.js", "inride.js", "routing.js", "account.js"];
const re = /\.(?:textContent|title|placeholder|innerText)\s*=\s*"([A-Z\u{1F000}-\u{1FFFF}][^"]*\s[^"]*\s?[^"]*)"\s*;/gu;
// Internal / test-mode strings that are intentionally not translated.
const allow = new Set(["Exit test mode", "Test mode off"]);
const bad = [];
for (const f of files) {
  const src = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", f), "utf8");
  let m;
  while ((m = re.exec(src))) {
    if (!allow.has(m[1]) && /[A-Za-z]{3,}\s+[A-Za-z]{2,}/.test(m[1])) bad.push(`${f}: "${m[1]}"`);
  }
}
if (bad.length) { console.error("Bare UI strings (wrap in T()/tr()):\n" + bad.join("\n")); process.exit(1); }
console.log("ok: no bare multi-word UI literals");
