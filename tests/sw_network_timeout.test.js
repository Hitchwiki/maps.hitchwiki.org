// sw.js races every network read against NET_TIMEOUT_MS.
//
// A roadside signal that connects but never answers used to hang the map forever:
// the fetch handler went network-first with a bare fetch() and only consulted the
// cache from .catch(), which a stalled-but-open socket never triggers. This pins
// the timeout fallback: when the network stalls, the cached copy is served.
//
// sw.js is a service-worker script (self, caches, OffscreenCanvas), so it cannot be
// require()d. Eval it against stubs and capture the 'fetch' listener it registers.

const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");

const SOURCE = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "sw.js"), "utf8");

function loadSw({ networkImpl, cacheStore }) {
  const listeners = {};
  const cache = {
    put: async () => {},
    match: async (url) => cacheStore[url],
  };
  const self = {
    addEventListener: (name, fn) => { listeners[name] = fn; },
    location: { hostname: "maps.hitchwiki.org" },
  };
  const caches = { open: async () => cache };
  const factory = new Function(
    "self", "caches", "fetch",
    `${SOURCE}\n return arguments;`,
  );
  factory(self, caches, networkImpl);
  return listeners;
}

test("a stalled network serves the cached page after the timeout", async () => {
  // Real ~4s wait for NET_TIMEOUT_MS — no fake timers, they don't drive the
  // promise chain cleanly on every node version.
  const cached = { body: "cached-map", clone: () => cached };
  const listeners = loadSw({
    networkImpl: () => new Promise(() => {}), // never resolves
    cacheStore: { "https://maps.hitchwiki.org/": cached },
  });

  let responded;
  const event = {
    request: { method: "GET", url: "https://maps.hitchwiki.org/", destination: "document" },
    respondWith: (p) => { responded = p; },
  };
  const started = Date.now();
  listeners.fetch(event);
  assert.strictEqual(await responded, cached);
  assert.ok(Date.now() - started >= 3000, "did not wait for the network timeout");
});

test("a working network is still served directly", async () => {
  const fresh = { body: "fresh-map", clone: () => fresh };
  const listeners = loadSw({
    networkImpl: async () => fresh,
    cacheStore: {},
  });

  let responded;
  const event = {
    request: { method: "GET", url: "https://maps.hitchwiki.org/", destination: "document" },
    respondWith: (p) => { responded = p; },
  };
  listeners.fetch(event);
  assert.strictEqual(await responded, fresh);
});
