const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const SOURCE = fs.readFileSync(
  path.join(__dirname, "..", "hitch", "static", "map.js"),
  "utf8",
);

test("share value test has a sticky control and treatment", () => {
  assert.match(
    SOURCE,
    /chooseVariant\("ride-share-value-v1", \["control", "help-friend"\]\)/,
  );
  assert.match(SOURCE, /hmTrack\("ride_share_exposure", \{ variant: shareVariant \}\)/);
  assert.match(SOURCE, /Help a friend try hitchhiking/);
  assert.match(SOURCE, /Share a real ride and show them where hitchhiking worked for you\./);
});

test("every share outcome carries the assigned variant", () => {
  assert.match(
    SOURCE,
    /hmTrack\("ride_share", Object\.assign\(\{ variant: shareVariant \}, properties\)\)/,
  );
  assert.doesNotMatch(SOURCE, /hmTrack\("ride_share", \{/);
  for (const action of ["dismiss", "clicked", "shared"]) {
    assert.ok(SOURCE.includes(`action: "${action}"`), `missing ${action} outcome`);
  }
  for (const event of [
    "ride_share_clicked",
    "ride_share_shared",
    "ride_share_dismissed",
  ]) {
    assert.ok(SOURCE.includes(`"${event}"`), `missing aggregate ${event} event`);
  }
});

// Umami's tracker keeps a single session-cache token that only advances once a
// request's response lands, and stamps every outgoing event with whatever value it
// currently holds. Firing two hmTrack calls in the same tick sends both with the
// stale token and the second collides server-side -- confirmed live: ride_share_clicked
// and ride_share_shared read exactly 0 events ever, against hundreds of real
// action=clicked/shared fires. The fix chains the outcome event off the primary call's
// own promise so it cannot start until the tracker says the first one is done.
test("the outcome event is not sent until the primary ride_share call resolves", async () => {
  const start = SOURCE.indexOf("function trackRideShare(properties) {");
  const end = SOURCE.indexOf("\n}\n", start) + 3;
  assert.ok(start !== -1 && end > start, "trackRideShare moved or was renamed");
  const block = SOURCE.slice(start, end);

  const calls = [];
  let resolvePrimary;
  const hmTrack = (name) => {
    calls.push(name);
    if (name === "ride_share") {
      return new Promise((res) => {
        resolvePrimary = res;
      });
    }
  };
  const factory = new Function("hmTrack", "shareVariant", `${block}\nreturn trackRideShare;`);
  const trackRideShare = factory(hmTrack, "control");

  trackRideShare({ action: "clicked" });
  assert.deepStrictEqual(calls, ["ride_share"], "outcome event must not fire in the same tick");

  await new Promise((res) => setTimeout(res, 20));
  assert.deepStrictEqual(calls, ["ride_share"], "outcome event must wait for the primary promise");

  resolvePrimary();
  await new Promise((res) => setTimeout(res, 0));
  assert.deepStrictEqual(calls, ["ride_share", "ride_share_clicked"]);
});
