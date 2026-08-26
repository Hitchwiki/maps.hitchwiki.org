const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const SOURCE = fs.readFileSync(
  path.join(__dirname, "..", "hitch", "static", "inride.js"),
  "utf8",
);

function coHitcherBlock() {
  const start = SOURCE.indexOf("coHitcherSheet(onStart)");
  const end = SOURCE.indexOf("// Slim give-up sheet", start);
  assert.ok(start > -1 && end > start, "could not locate coHitcherSheet");
  return SOURCE.slice(start, end);
}

test("dismissing optional co-hitcher selection preserves the start intent", () => {
  const block = coHitcherBlock();
  assert.match(block, /closeX\.addEventListener\("click", function \(\) \{ close\("close-x"\); \}\)/);
  assert.match(block, /scrim\.addEventListener\("click", function \(\) \{ close\("scrim"\); \}\)/);
  assert.match(
    block,
    /if \(reason === "scrim" \|\| reason === "close-x"\) onStart\(selected\.slice\(\)\)/,
  );
});

test("explicit start and forced close cannot double-start", () => {
  const block = coHitcherBlock();
  assert.match(block, /let closed = false;\s*function close\(reason\) \{\s*if \(closed\) return;\s*closed = true;/);
  assert.match(block, /close\("button"\);\s*onStart\(list\);/);
  // journeyUI's one-dialog-at-a-time guard invokes close() with no reason.
  // That must not satisfy either dismissal reason above.
  assert.doesNotMatch(block, /if \(!reason\)[^\n]*onStart/);
});
