"use strict";

// B536 / IDEAS.md #227: on a ride leg of a route result, surface what
// hitchhikers wrote about the spot it boards at — mean rating, median recorded
// wait, and the MOST RECENT substantial comment with its date (not the
// longest). Pulled from the same dist/rides/by-spot/<id>.json the spot pane
// uses. Exercised headlessly per the CLAUDE.md note on running routing.js
// under node.

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const source = fs.readFileSync(
  path.join(__dirname, "..", "hitch", "static", "routing.js"),
  "utf8"
);

// Minimal DOM: just enough for fillLegEvidence's createElement / appendChild /
// textContent and the module's top-level guards.
function makeEl() {
  return {
    className: "",
    textContent: "",
    children: [],
    appendChild(c) { this.children.push(c); return c; },
    querySelector: () => null,
  };
}

const perSpot = {
  rides: [
    { rating: 5, wait: 10, comment: "short", submission_time: "2020-01-01 09:00" },
    {
      rating: 3,
      wait: 40,
      comment: "  This is by far the longest comment on the spot, a whole paragraph about the on-ramp geometry and sight lines and where to stand, written years ago.  ",
      submission_time: "2019-06-06 12:00",
    },
    {
      rating: 4,
      wait: 20,
      comment: "Police moved me on after 20 minutes here last week, try the lay-by 200m north instead.",
      ride_datetime: "2026-08-20 15:00",
      submission_time: "2026-08-21 10:00",
    },
  ],
};

let tracked = [];
let bySpotFetched = "";
const sandbox = {
  window: { hmTrack: (name, props) => tracked.push([name, props]) },
  document: {
    createElement: makeEl,
    createTextNode: (t) => ({ textContent: t }),
    querySelector: () => null,
  },
  fetch: (url) => {
    if (url.indexOf("/rides/by-spot/") === 0) {
      bySpotFetched = url;
      return Promise.resolve({ ok: true, json: () => Promise.resolve(perSpot) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  },
  setTimeout: (fn) => fn(),
  L: { latLng: (a, b) => ({ a, b }) },
};
sandbox.window.window = sandbox.window;
vm.createContext(sandbox);
vm.runInContext(source, sandbox);

const { fillLegEvidence } = sandbox.window.RoutingInternals;
assert.ok(typeof fillLegEvidence === "function", "fillLegEvidence is exposed for tests");

const body = makeEl();
fillLegEvidence(body, [50.12345, 14.67891]);

// Let the fetch promise chain settle.
(async () => {
  await new Promise((r) => setTimeout(r, 20));
  assert.strictEqual(bySpotFetched, "/rides/by-spot/50.12345_14.67891.json", "fetched the per-spot file");
  assert.strictEqual(body.children.length, 1, "one .rp-evi block appended");
  const box = body.children[0];
  assert.strictEqual(box.className, "rp-evi");

  const sum = box.children[0].textContent;
  assert.ok(sum.indexOf("★ 4.0") === 0, "mean rating (5+3+4)/3 = 4.0, got: " + sum);
  assert.ok(sum.indexOf("20m wait") !== -1, "median wait of [10,20,40] is 20, got: " + sum);
  assert.ok(sum.indexOf("3 logged rides") !== -1, "ride count, got: " + sum);

  const q = box.children[1].textContent;
  assert.ok(q.indexOf("Police moved me on") !== -1,
    "quotes the MOST RECENT substantial comment, not the longest, got: " + q);
  assert.ok(q.indexOf("longest comment") === -1, "does not quote the older longer comment");

  const dateEl = box.children[1].children[1];
  assert.strictEqual(dateEl.className, "rp-evi-d");
  assert.strictEqual(dateEl.textContent, "2026-08-20", "date is the ride_datetime day");

  assert.strictEqual(tracked[0][0], "route_evidence_shown");
  assert.strictEqual(tracked[0][1].comment, 1);
  console.log("route_evidence_card.test.js OK");
})();
