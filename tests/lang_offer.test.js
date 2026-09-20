// The language offer: a pill in the brand bar on unprefixed pages when the browser's first
// language has a translation. Runs the real inline script from map.html against a stub DOM.
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const html = fs.readFileSync(path.join(__dirname, "../hitch/templates/map.html"), "utf8");
const start = html.indexOf("{# Language offer.");
assert(start > 0, "language offer block present");
const s = html.indexOf("<script>", start) + "<script>".length;
const src = html.slice(s, html.indexOf("</script>", s));

function run({ activeLang = "en", langs = ["de-DE"], seen, available = ["de", "fr"] }) {
  const store = seen === undefined ? {} : { hmLangOfferShown: String(seen) };
  const inserted = [];
  const events = [];
  const handlers = {};
  const picker = { parentNode: { insertBefore: (el) => inserted.push(el) } };
  const el = () => ({ attrs: {}, setAttribute(k, v) { this.attrs[k] = v; }, addEventListener: (t, f) => (handlers[t] = f) });
  const doc = {
    getElementById: (id) => (id === "lang-picker" ? picker : null),
    createElement: () => el(),
    querySelector: (q) => {
      if (q === "#lang-picker .lang-picker-item.active") return { getAttribute: () => activeLang };
      const m = q.match(/hreflang="(\w+)"/);
      if (m && available.includes(m[1])) return { getAttribute: () => "/" + m[1], textContent: " F  Name " };
      return null;
    },
  };
  const ctx = {
    document: doc,
    navigator: { languages: langs },
    localStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => (store[k] = v) },
    window: { hmTrack: (n, p) => events.push([n, p.lang]) },
    parseInt, String,
  };
  vm.runInNewContext(src, ctx);
  return { inserted, events, store, click: () => handlers.click && handlers.click() };
}

let r = run({});
assert.strictEqual(r.inserted.length, 1, "German browser on an English page gets the pill");
assert.strictEqual(r.inserted[0].href, "/de");
assert.strictEqual(r.inserted[0].textContent, "F Name");
assert.deepStrictEqual(r.events, [["lang_banner_shown", "de"]]);
assert.strictEqual(r.store.hmLangOfferShown, "1");
r.click();
assert.strictEqual(r.store.hmLangOfferShown, "99", "click retires the offer");
assert.deepStrictEqual(r.events[1], ["lang_banner_clicked", "de"]);

assert.strictEqual(run({ langs: ["en-GB", "de"] }).inserted.length, 0, "English first: no offer");
assert.strictEqual(run({ langs: ["xx-YY"] }).inserted.length, 0, "no translation: no offer");
assert.strictEqual(run({ activeLang: "de" }).inserted.length, 0, "already on a prefixed page: no offer");
assert.strictEqual(run({ seen: 5 }).inserted.length, 0, "stops after 5 shows");
assert.strictEqual(run({ seen: 4 }).inserted.length, 1, "still shows on the 5th load");
assert.strictEqual(run({ langs: ["fr-CA"] }).inserted[0].href, "/fr", "regional tag maps to the base language");
console.log("lang_offer ok");
