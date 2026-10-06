// #660: bare-URL first visit frames the visitor's country (language region), 50/50 A/B.
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const SOURCE = fs.readFileSync(path.join(__dirname, "../hitch/static/map.js"), "utf8");
const start = SOURCE.indexOf("const START_VIEW_REGIONS");
const end = SOURCE.indexOf("// Create the Leaflet map synchronously");
const code = SOURCE.slice(start, end) + "\nreturn startViewForVisitor;";

function run({ hash = "", pathname = "/", search = "", languages, variant = "region" }) {
  const events = [];
  const fn = new Function("location", "navigator", "window", code)(
    { hash, pathname, search },
    { languages, language: languages[0] },
    { hmVariant: () => variant, hmTrack: (n, d) => events.push([n, d.variant]) },
  );
  return { view: fn(), events };
}

test("region arm frames the language region and tracks assignment", () => {
  const r = run({ languages: ["en-US", "en"] });
  assert.deepStrictEqual(r.view, [39, -98, 4]);
  assert.deepStrictEqual(r.events, [["start_view_assigned", "region"]]);
});

test("world arm keeps the default view but is still counted", () => {
  const r = run({ languages: ["de-DE"], variant: "world" });
  assert.strictEqual(r.view, null);
  assert.deepStrictEqual(r.events, [["start_view_assigned", "world"]]);
});

test("hash, path, query or unknown region: not eligible, not counted", () => {
  for (const o of [{ hash: "#map=5/1/2" }, { pathname: "/spot/1_2" }, { search: "?lat=1&lon=2" }, { languages: ["en"] }, { languages: ["xx-ZZ"] }]) {
    const r = run({ languages: ["en-US"], ...o });
    assert.strictEqual(r.view, null);
    assert.deepStrictEqual(r.events, []);
  }
});

test("first language with a known region wins", () => {
  assert.deepStrictEqual(run({ languages: ["en", "pl-PL"] }).view, [52, 19, 5]);
});

test("createMap uses the start view", () => {
  assert.match(SOURCE, /center: startView \? \[startView\[0\], startView\[1\]\] : \[0, 0\]/);
});

test("the initial-view fallback does not overwrite the region start view", () => {
  assert.match(SOURCE, /window\.hmStartView = startView;/);
  assert.match(SOURCE, /if \(window\.hmStartView\) \{\s*map\.setView\(\[window\.hmStartView\[0\]/);
});
