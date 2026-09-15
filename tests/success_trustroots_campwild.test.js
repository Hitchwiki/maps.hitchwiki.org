const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const mapSource = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "map.js"), "utf8");
const start = mapSource.indexOf("function renderTrustrootsNudge()");
const end = mapSource.indexOf("// #191 / EXP-428", start);
const helperSource = mapSource.slice(start, end);

function loadHelper({ hasTrustrootsNode = true, hasCampwildNode = true } = {}) {
  const events = [];
  function makeNote() {
    return {
      textContent: "old",
      style: { display: "none" },
      children: [],
      appendChild(child) { this.children.push(child); },
    };
  }
  const trustrootsNote = hasTrustrootsNode ? makeNote() : null;
  const campwildNote = hasCampwildNode ? makeNote() : null;
  const sandbox = {
    $$: (sel) => {
      if (sel === "#success-trustroots-nudge") return trustrootsNote;
      if (sel === "#success-campwild-nudge") return campwildNote;
      return null;
    },
    tr: (s) => s,
    hmTrack: (name, props) => events.push({ name, props }),
    document: { createElement: () => ({}) },
  };
  vm.createContext(sandbox);
  vm.runInContext(
    helperSource +
      "; this.renderTrustrootsNudge = renderTrustrootsNudge; this.renderCampwildNudge = renderCampwildNudge;",
    sandbox,
  );
  return {
    runTrustroots: () => sandbox.renderTrustrootsNudge(),
    runCampwild: () => sandbox.renderCampwildNudge(),
    events,
    trustrootsNote,
    campwildNote,
  };
}

test("renderTrustrootsNudge shows a Trustroots link and tracks shown/clicked", () => {
  const h = loadHelper();
  h.runTrustroots();
  assert.strictEqual(h.trustrootsNote.style.display, "block");
  const link = h.trustrootsNote.children[h.trustrootsNote.children.length - 1];
  assert.strictEqual(link.href, "https://www.trustroots.org");
  assert.strictEqual(link.target, "_blank");
  assert.strictEqual(link.rel, "noopener");
  assert.match(link.textContent, /Trustroots/);
  assert.strictEqual(h.events[0].name, "trustroots_nudge_shown");
  assert.strictEqual(h.events[0].props.source, "success-overlay");
  link.onclick();
  assert.strictEqual(h.events[1].name, "trustroots_nudge_clicked");
  assert.strictEqual(h.events[1].props.source, "success-overlay");
});

test("renderCampwildNudge shows a campwild.org link and tracks shown/clicked", () => {
  const h = loadHelper();
  h.runCampwild();
  assert.strictEqual(h.campwildNote.style.display, "block");
  const link = h.campwildNote.children[h.campwildNote.children.length - 1];
  assert.strictEqual(link.href, "https://campwild.org");
  assert.strictEqual(link.target, "_blank");
  assert.strictEqual(link.rel, "noopener");
  assert.match(link.textContent, /campwild\.org/);
  assert.strictEqual(h.events[0].name, "campwild_nudge_shown");
  assert.strictEqual(h.events[0].props.source, "success-overlay");
  link.onclick();
  assert.strictEqual(h.events[1].name, "campwild_nudge_clicked");
  assert.strictEqual(h.events[1].props.source, "success-overlay");
});

test("both nudges no-op gracefully against an old cached overlay missing the note element", () => {
  const h = loadHelper({ hasTrustrootsNode: false, hasCampwildNode: false });
  assert.doesNotThrow(() => h.runTrustroots());
  assert.doesNotThrow(() => h.runCampwild());
  assert.strictEqual(h.events.length, 0);
});

test("the success overlay markup has placeholders for both nudges", () => {
  const html = fs.readFileSync(path.join(__dirname, "..", "hitch", "templates", "map.html"), "utf8");
  assert.match(html, /id="success-trustroots-nudge"/);
  assert.match(html, /id="success-campwild-nudge"/);
});

test("showSuccessOverlay renders both nudges", () => {
  assert.match(mapSource, /renderTrustrootsNudge\(\);/);
  assert.match(mapSource, /renderCampwildNudge\(\);/);
});
