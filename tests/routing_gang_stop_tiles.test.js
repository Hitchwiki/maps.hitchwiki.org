const assert = require("assert");
const F = require("../hitch/static/routing_gang_fallback.js");

// Route Dresden-ish -> Berlin-ish crosses lat tiles 51 and 52, lon tile 13.
const pts = [[51.05, 13.74], [51.99, 13.5], [52.01, 13.4]];
assert(F.inCoverage(pts));
assert(!F.inCoverage([[10, 13]]));        // outside the pull
assert(!F.inCoverage([[51, 60]]));
const keys = F.tileKeys(pts, 0.01).sort();
assert.deepStrictEqual(keys, ["51_13", "52_13"]);
// A point 0.005 deg under a tile edge also asks for the tile above it.
assert(F.tileKeys([[51.995, 13.5]], 0.01).includes("52_13"));

const tileA = [["f", 51.0501, 13.7401, "Aral"], ["f", 51.5, 13.0, "far"], ["j", 51.99, 13.51, "AS Test"]];
const tileB = [["s", 52.0, 13.4, ""], ["r", 52.9, 13.9, "far rest"]];
const els = F.tileElements([tileA, tileB], pts, 0.01);
assert.strictEqual(els.length, 3);        // the two far ones are dropped
const fuel = els.find(e => e.tags.amenity === "fuel");
assert.strictEqual(fuel.tags.name, "Aral");
assert.strictEqual(fuel.type, "node");
assert.strictEqual(els.find(e => e.tags.highway === "motorway_junction").tags.name, "AS Test");
assert.strictEqual(els.find(e => e.tags.highway === "services").tags.name, undefined);
assert.strictEqual(new Set(els.map(e => e.type + e.id)).size, 3);   // unique ids, the page de-dupes on type+id
console.log("ok");
