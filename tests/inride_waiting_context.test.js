// journeyUI._spotContextLine: one line of a spot's OWN logged history for the
// waiting dock. inride.js is a browser IIFE, so it's loaded the way CLAUDE.md
// describes for routing.js — stub globals, eval, drive window.inride directly.

const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const RideSubmit = require("../hitch/static/ride_submit.js");
const SOURCE = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "inride.js"), "utf8");

function loadInride() {
  const window = {
    RideSubmit,
    hmTrack: () => {},
    addEventListener: () => {},
    location: { origin: "https://maps.example", hash: "", search: "" },
  };
  const sandbox = {
    window,
    self: window,
    document: { addEventListener: () => {}, createElement: () => ({ style: {}, classList: { add() {}, remove() {} } }), body: { classList: { add() {}, remove() {} } } },
    localStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
    sessionStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
    navigator: { onLine: true, geolocation: {} },
    console,
    setInterval: () => 0,
    clearInterval: () => {},
    setTimeout: () => 0,
    clearTimeout: () => {},
    Promise, Set, Map, JSON, Date, Math, URLSearchParams, isFinite, isNaN,
    fetch: () => Promise.resolve({ ok: false }),
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(SOURCE, sandbox);
  return window.inride;
}

const NOW = Date.parse("2026-08-30T12:00:00Z");

test("thin spots (<3 rides) get no context line", () => {
  const ui = loadInride().journeyUI;
  assert.strictEqual(ui._spotContextLine({ wait: 20 }, [{}, {}], NOW), null);
  assert.strictEqual(ui._spotContextLine({}, [], NOW), null);
});

test("a well-covered spot renders wait, ride count and last-hitched age", () => {
  const ui = loadInride().journeyUI;
  const rides = [
    { ride_datetime: "2026-08-24T09:00:00Z" },
    { submission_time: "2026-08-10T09:00:00Z" },
    { ride_datetime: "2026-07-01T09:00:00Z" },
  ];
  const line = ui._spotContextLine({ wait: 24.6 }, rides, NOW);
  assert.strictEqual(line, "~25 min typical wait · 3 rides logged · last hitched 6d ago");
});

test("no wait figure just drops that segment", () => {
  const ui = loadInride().journeyUI;
  const rides = [
    { ride_datetime: "2026-08-30T06:00:00Z" },
    { ride_datetime: "2026-08-29T06:00:00Z" },
    { ride_datetime: "2026-08-28T06:00:00Z" },
  ];
  assert.strictEqual(ui._spotContextLine({}, rides, NOW), "3 rides logged · last hitched today");
});
