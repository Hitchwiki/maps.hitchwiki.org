const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");
const SOURCE = fs.readFileSync(path.join(__dirname, "../hitch/static/inride.js"), "utf8");

test("give-up at <=1 min offers the discard exit before the sheet", () => {
  const i = SOURCE.indexOf("journeyFlow.giveUp = function");
  assert.ok(i > 0);
  const body = SOURCE.slice(i, i + 2200);
  assert.match(body, /waitMin <= 1 && !journeyFlow\._giveUpConfirmed/);
  assert.match(body, /journeyFlow\._discardCancel\(j\)/);
  assert.ok(body.indexOf("_discardCancel") < body.indexOf("journeyUI.giveUpSheet"));
});
