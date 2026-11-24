const test = require("node:test"), assert = require("node:assert"), fs = require("fs");
const src = fs.readFileSync(__dirname + "/../hitch/static/map.js", "utf8");
test("exit-area count shown without a button", () => {
  assert.match(src, /exitCount = exitIdx >= 0/);
  assert.match(src, /\$\{hitchwikiGapPrompt\}\$\{exitCount\}\$\{spotWikiExcerpt\}/);
  assert.match(src, /hitchhikers started here since Oct 2024/);
  assert.ok(!/spot-official-stop-wanted/.test(src));
});
