const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const mapSource = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "map.js"), "utf8");
const start = mapSource.indexOf("const WIKI_CONTRIBUTE_COMMENT_CHARS");
const end = mapSource.indexOf("// Builds the shareable image", start);
const helperSource = mapSource.slice(start, end);

function loadHelper({ comment = "x".repeat(200), wiki = true, longNoteCount = 0, failCount = false } = {}) {
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
    tr: (s) => s,
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
        ok: true,
        json: async () => ({ spot: { hitchwiki_article: "https://hitchwiki.org/en/Dresden" } }),
      };
    },
    document: { createElement: () => ({}) },
    Number,
    String,
    encodeURIComponent,
  };
  vm.createContext(sandbox);
  vm.runInContext(helperSource + "; this.renderWikiContributionNudge = renderWikiContributionNudge", sandbox);
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

test("short notes and spots without a wiki article do no detail fetch", async () => {
  const short = loadHelper({ comment: "too short" });
  await short.run();
  assert.strictEqual(short.fetches.length, 0);
  assert.strictEqual(short.note.style.display, "none");

  const noWiki = loadHelper({ wiki: false });
  await noWiki.run();
  assert.strictEqual(noWiki.fetches.length, 0);
  assert.strictEqual(noWiki.note.style.display, "none");
});

test("both ride-entry paths hand the comment to the success overlay", () => {
  const form = fs.readFileSync(path.join(__dirname, "..", "hitch", "templates", "ride_form.html"), "utf8");
  const inride = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "inride.js"), "utf8");
  assert.match(form, /comment: document\.querySelector\('textarea\[name="comment"\]'/);
  assert.match(inride, /comment: body\.comment \|\| ""/);
});
