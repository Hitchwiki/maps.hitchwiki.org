// #787: #search/<q> runs the place search and drops the hash.
const fs = require("fs");
const assert = require("assert");
const src = fs.readFileSync(__dirname + "/../hitch/static/map.js", "utf8");

assert(/window\.runPlaceSearch = function/.test(src), "runPlaceSearch exposed");
assert(/\^#search\\\/\(\.\+\)\$/.test(src), "search hash regex present");
// the handler must precede the #location branch and clear the hash before searching
const iHandler = src.indexOf("const searchHash");
const iLocation = src.indexOf('if (mainArgs[0] == "location")');
assert(iHandler > 0 && iHandler < iLocation, "handler runs before navigation branches");
const block = src.slice(iHandler, iLocation);
assert(block.indexOf('url.hash = ""') < block.indexOf("runPlaceSearch(q)"), "hash dropped before search");
// the regex itself
const re = /^#search\/(.+)$/;
assert.strictEqual(re.exec("#search/Teltow%2C%20DE")[1], "Teltow%2C%20DE");
assert.strictEqual(re.exec("#map=5/1/2"), null);
console.log("ok");
