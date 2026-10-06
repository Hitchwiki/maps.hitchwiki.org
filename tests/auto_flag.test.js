const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const src = fs.readFileSync(__dirname + "/../hitch/templates/base.html", "utf8");

test("every tracked event carries an auto flag from webdriver/HeadlessChrome", () => {
  assert.match(src, /var AUTO = "n";/);
  assert.match(src, /navigator\.webdriver === true \|\| \/HeadlessChrome\/\.test\(navigator\.userAgent\)/);
  assert.match(src, /var out = \{ shell: SURFACE, auto: AUTO \};/);
});
