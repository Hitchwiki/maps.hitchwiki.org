// #651: first-journey waiting row. inride.js is a browser IIFE; same stub-and-eval
// loader as inride_waiting_context.test.js.
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const RideSubmit = require("../hitch/static/ride_submit.js");
const SOURCE = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "inride.js"), "utf8");

function el() {
  return { style: {}, children: [], attrs: {}, listeners: {}, classList: { add() {}, remove() {} },
    appendChild(c) { this.children.push(c); }, setAttribute(k, v) { this.attrs[k] = v; },
    addEventListener(t, f) { this.listeners[t] = f; } };
}

function load(store) {
  const tracked = [];
  const window = { RideSubmit, hmTrack: (n, p) => tracked.push([n, p]), addEventListener: () => {}, location: { origin: "https://m", hash: "", search: "" } };
  const sandbox = {
    window, self: window,
    document: { addEventListener: () => {}, createElement: () => el(), createTextNode: (t) => ({ text: t }), body: { classList: { add() {}, remove() {} } } },
    localStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = v; }, removeItem: () => {} },
    sessionStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
    navigator: { onLine: true, geolocation: {} }, console,
    setInterval: () => 0, clearInterval: () => {}, setTimeout: () => 0, clearTimeout: () => {},
    Promise, Set, Map, JSON, Date, Math, URLSearchParams, isFinite, isNaN, parseInt, String,
    fetch: () => Promise.resolve({ ok: false }),
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(SOURCE, sandbox);
  return { ui: window.inride.journeyUI, tracked };
}

test("chat arm links the Matrix room with the chat-place tag", () => {
  const { ui } = load({});
  const row = ui._buildFirstWaitRow("chat");
  const a = row.children.find((c) => c.href);
  assert.match(a.href, /^https:\/\/matrix\.to\//);
  assert.strictEqual(a.attrs["data-chat-place"], "journey_waiting_first");
});

test("stories arm links the wiki first-timer article with a ref", () => {
  const { ui } = load({});
  const a = ui._buildFirstWaitRow("stories").children[0];
  assert.strictEqual(a.href, "https://hitchwiki.org/en/First_time_hitchhiking?ref=maps-firstwait");
});

test("clicking tracks the arm", () => {
  const { ui, tracked } = load({});
  const a = ui._buildFirstWaitRow("stories").children[0];
  a.listeners.click();
  assert.strictEqual(JSON.stringify(tracked.pop()), JSON.stringify(["first_wait_people_clicked", { arm: "stories" }]));
});
