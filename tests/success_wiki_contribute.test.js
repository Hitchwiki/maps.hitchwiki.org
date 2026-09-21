const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const mapSource = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "map.js"), "utf8");
const start = mapSource.indexOf("const WIKI_CONTRIBUTE_COMMENT_CHARS");
const end = mapSource.indexOf("// Builds the shareable image", start);
const helperSource = mapSource.slice(start, end);
// The nudge's map arm reuses the module-scope wiki-URL parser and base constant,
// which live outside the sliced block — extract them so the sandbox runs the real
// code rather than a stub that could drift from it.
const parseStart = mapSource.indexOf("// Parse a spot's hitchwiki_article/hitchwiki_map URL");
const parseEnd = mapSource.indexOf("\n}", mapSource.indexOf("function parseSpotWikiUrl", parseStart)) + 2;
const urlHelperSource =
  'const COUNTRY_WIKI_BASE = "https://hitchwiki.org/en/";\n' + mapSource.slice(parseStart, parseEnd);

function loadHelper({ comment = "x".repeat(200), wiki = true, longNoteCount = 0, failCount = false, spot = null, spotOk = true } = {}) {
  const events = [];
  const fetches = [];
  const note = {
    textContent: "old",
    style: { display: "block" },
    children: [],
    appendChild(child) { this.children.push(child); },
  };
  const sandbox = {
    allMarkers: [{
      options: {
        spotId: "51.08170_13.73629",
        _data: wiki ? { wiki: true } : {},
      },
    }],
    $$: () => note,
    tr: (s, vars) => s.replace(/\{(\w+)\}/g, (_, k) => String((vars || {})[k])),
    hmTrack: (name, props) => events.push({ name, props }),
    fetch: async (url) => {
      fetches.push(url);
      if (url === "/me/longnote_count.json") {
        if (failCount) throw new Error("network");
        return {
          ok: true,
          json: async () => ({ count: longNoteCount, repeat_writer: longNoteCount >= 4 }),
        };
      }
      return {
        ok: spotOk,
        json: async () => ({ spot: spot || { hitchwiki_article: "https://hitchwiki.org/en/Dresden" } }),
      };
    },
    document: { createElement: () => ({}) },
    Number,
    String,
    encodeURIComponent,
  };
  vm.createContext(sandbox);
  vm.runInContext(
    urlHelperSource + "\n" + helperSource + "; this.renderWikiContributionNudge = renderWikiContributionNudge",
    sandbox,
  );
  return {
    run: () => sandbox.renderWikiContributionNudge({
      pickupLat: 51.0817,
      pickupLon: 13.73629,
      comment,
    }),
    events,
    fetches,
    note,
  };
}

test("a long note at a wiki-linked spot gets the contribution invitation", async () => {
  const h = loadHelper();
  await h.run();
  assert.deepStrictEqual(h.fetches, [
    "/rides/by-spot/51.08170_13.73629.json",
    "/me/longnote_count.json",
  ]);
  assert.strictEqual(h.note.style.display, "block");
  const link = h.note.children[h.note.children.length - 1];
  assert.strictEqual(link.href, "https://hitchwiki.org/en/Dresden");
  assert.strictEqual(h.events[0].name, "wiki_contribute_shown");
  assert.strictEqual(h.events[0].props.source, "success-overlay");
  assert.strictEqual(h.events[0].props.repeat_writer, false);
  link.onclick();
  assert.strictEqual(h.events[1].name, "wiki_contribute_clicked");
  assert.strictEqual(h.events[1].props.repeat_writer, false);
});

test("a proven repeat note-writer gets the warmer ask and a flagged event", async () => {
  const h = loadHelper({ longNoteCount: 7 });
  await h.run();
  assert.strictEqual(h.note.style.display, "block");
  const link = h.note.children[h.note.children.length - 1];
  assert.strictEqual(link.href, "https://hitchwiki.org/en/Dresden");
  assert.match(link.textContent, /what you know/);
  assert.strictEqual(h.events[0].name, "wiki_contribute_shown");
  assert.strictEqual(h.events[0].props.repeat_writer, true);
  link.onclick();
  assert.strictEqual(h.events[1].props.repeat_writer, true);
});

test("a failed longnote lookup still shows the standard invitation", async () => {
  const h = loadHelper({ failCount: true });
  await h.run();
  assert.strictEqual(h.note.style.display, "block");
  const link = h.note.children[h.note.children.length - 1];
  assert.strictEqual(link.href, "https://hitchwiki.org/en/Dresden");
  assert.strictEqual(h.events[0].props.repeat_writer, false);
});

test("short notes do no detail fetch", async () => {
  const short = loadHelper({ comment: "too short" });
  await short.run();
  assert.strictEqual(short.fetches.length, 0);
  assert.strictEqual(short.note.style.display, "none");
});

test("a spot with no wiki flag still gets the invitation (the marker flag is no longer a gate)", async () => {
  const h = loadHelper({ wiki: false });
  await h.run();
  assert.strictEqual(h.note.style.display, "block");
  assert.strictEqual(h.events[0].props.arm, "article");
});

test("no article but a nearby one: distance-labelled invitation, arm=nearby", async () => {
  const h = loadHelper({
    wiki: false,
    spot: { hitchwiki_nearby: { url: "https://hitchwiki.org/en/Prague", title: "Prague", km: 11.3 } },
  });
  await h.run();
  assert.strictEqual(h.note.style.display, "block");
  const link = h.note.children[h.note.children.length - 1];
  assert.strictEqual(link.href, "https://hitchwiki.org/en/Prague");
  assert.strictEqual(h.events[0].name, "wiki_contribute_shown");
  assert.strictEqual(h.events[0].props.arm, "nearby");
  link.onclick();
  assert.strictEqual(h.events[1].props.arm, "nearby");
});

test("neither an article nor a nearby one, or a missing detail file: no invitation", async () => {
  const none = loadHelper({ wiki: false, spot: {} });
  await none.run();
  assert.strictEqual(none.note.style.display, "none");
  assert.strictEqual(none.events.length, 0);

  const missing = loadHelper({ wiki: false, spotOk: false });
  await missing.run();
  assert.strictEqual(missing.note.style.display, "none");
});

test("a spot covered by a Hitchwiki map page (no article, no nearby): titled invitation, arm=map", async () => {
  const h = loadHelper({
    wiki: false,
    spot: { hitchwiki_map: "https://hitchwiki.org/en/Zürich" },
  });
  await h.run();
  assert.strictEqual(h.note.style.display, "block");
  const link = h.note.children[h.note.children.length - 1];
  assert.strictEqual(link.href, "https://hitchwiki.org/en/Zürich");
  assert.match(link.textContent, /Zürich/);
  assert.strictEqual(h.events[0].name, "wiki_contribute_shown");
  assert.strictEqual(h.events[0].props.arm, "map");
  link.onclick();
  assert.strictEqual(h.events[1].name, "wiki_contribute_clicked");
  assert.strictEqual(h.events[1].props.arm, "map");
});

test("a map URL with a section anchor still invites to the page, title without the anchor", async () => {
  const h = loadHelper({
    wiki: false,
    spot: { hitchwiki_map: "https://hitchwiki.org/en/Luxembourg (City)#Motorway_exit_for_Brussels" },
  });
  await h.run();
  const link = h.note.children[h.note.children.length - 1];
  assert.strictEqual(link.href, "https://hitchwiki.org/en/Luxembourg (City)#Motorway_exit_for_Brussels");
  assert.match(link.textContent, /Luxembourg \(City\)$/);
  assert.strictEqual(h.events[0].props.arm, "map");
});

test("an article still beats the map page, and the map page beats the nearby article", async () => {
  const both = loadHelper({
    wiki: false,
    spot: {
      hitchwiki_article: "https://hitchwiki.org/en/Dresden",
      hitchwiki_map: "https://hitchwiki.org/en/Zürich",
    },
  });
  await both.run();
  assert.strictEqual(both.events[0].props.arm, "article");

  const mapNearby = loadHelper({
    wiki: false,
    spot: {
      hitchwiki_map: "https://hitchwiki.org/en/Zürich",
      // show.py never emits both, but precedence is pinned in case it ever does
      hitchwiki_nearby: { url: "https://hitchwiki.org/en/Prague", title: "Prague", km: 11.3 },
    },
  });
  await mapNearby.run();
  assert.strictEqual(mapNearby.events[0].props.arm, "map");
});

test("both ride-entry paths hand the comment to the success overlay", () => {
  const form = fs.readFileSync(path.join(__dirname, "..", "hitch", "templates", "ride_form.html"), "utf8");
  const inride = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "inride.js"), "utf8");
  assert.match(form, /comment: document\.querySelector\('textarea\[name="comment"\]'/);
  assert.match(inride, /comment: body\.comment \|\| ""/);
});
