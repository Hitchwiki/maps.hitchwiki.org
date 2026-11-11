"use strict";
const assert = require("assert");
const W = require("../hitch/static/wiki_exit.js");
const cities = [{ title: "Berlin", la: 52.52, lo: 13.4, h: ["Northwest towards Hamburg", "South towards Dresden", "East, South towards Poland"] }];
let r = W.pick(cities, [52.5, 13.4], [53.55, 9.99], 12);
assert.strictEqual(r.heading, "Northwest towards Hamburg");
assert.ok(r.url.startsWith("https://hitchwiki.org/en/Berlin#"));
assert.strictEqual(W.pick(cities, [48.1, 11.5], [53.55, 9.99], 12), null, "far start -> none");
assert.strictEqual(W.pick(cities, [52.5, 13.4], [52.5, 20], 12).heading, "East, South towards Poland");
assert.deepStrictEqual(W.headingAngles("East, South towards X"), [90, 180]);
assert.strictEqual(W.pick(cities, [52.5, 13.4], [52.5, 5], 12), null, "no west heading -> none");
console.log("wiki_exit ok");
{
  const r = W.pick([{ title: "Aachen", la: 50.775, lo: 6.082, h: ["West towards Netherlands {{Autobahn|4}} {{E|314}}, Belgium"] }], [50.77, 6.08], [51.0, 4.0], 12);
  assert.strictEqual(r.heading, "West towards Netherlands , Belgium".replace(" ,", ","));
  assert.ok(r.url.indexOf("#") === -1, "template headings link the page only");
}
