// IDEAS #531: a week after a driver pledge, ask once (max twice) whether it happened.
const fs = require("fs");
const assert = require("assert");
const inr = fs.readFileSync(__dirname + "/../hitch/static/inride.js", "utf8");
const map = fs.readFileSync(__dirname + "/../hitch/static/map.js", "utf8");
// All three pledge surfaces stamp time + surface.
assert(map.includes('noteDriverPledgeTime("success_overlay")'));
assert(map.includes('noteDriverPledgeTime("spot_country_contact")'));
assert(inr.includes('localStorage.setItem("hmDriverPledgeSurface", "race_banner")'));
assert(inr.includes('localStorage.setItem("hmDriverPledgedAt", String(Date.now()))'));
const start = inr.indexOf("const driverPledgeFollowup = {");
const body = inr.slice(start, inr.indexOf("// ── thinCoverageBanner", start));
assert(body.includes("WAIT_MS: 7 * 86400000") && body.includes("MAX_ASKS: 2"));
// Non-pledgers and answered devices never see it; legacy pledgers are stamped, not asked.
assert(body.includes('if (!localStorage.getItem("hmDriverPledgeMade")) return;'));
assert(body.includes('if (localStorage.getItem("hmDriverFollowupDone")) return;'));
assert(/if \(!\(at > 0\)\) \{ localStorage\.setItem\("hmDriverPledgedAt"[^}]*return; \}/.test(body));
// Never over a journey, an open dialog, or a shared route link.
assert(body.includes("journeyStore.get() || journeyUI._openDialog"));
assert(body.includes("dir"));
// Events.
for (const e of ["driver_pledge_followup_shown", "driver_pledge_followup_answered", "driver_pledge_followup_dismissed"]) assert(body.includes(e), e);
assert(/answer\("yes"\)/.test(body) && /answer\("not_yet"\)/.test(body));
// Wired after the race banner / thin coverage, delayed.
assert(/setTimeout\(driverPledgeFollowup\.check, 6000\)/.test(inr));
console.log("driver_pledge_followup ok");

// Behaviour: run check() itself against a stubbed browser (fresh / due / done / capped / route links).
const vm = require("vm");
const DAY = 86400000;
function run(store, loc, extra) {
  const ls = Object.assign({}, store);
  const events = [], dialogs = [];
  const ctx = {
    localStorage: { getItem: k => (k in ls ? ls[k] : null), setItem: (k, v) => { ls[k] = String(v); } },
    location: loc, Date, Number, Math,
    journeyStore: { get: () => (extra && extra.journey) || null },
    journeyUI: { _openDialog: (extra && extra.dialog) || null, dialog: d => dialogs.push(d) },
    hmTrack: (n, p) => events.push(n), T: x => x,
  };
  vm.createContext(ctx);
  vm.runInContext(body.slice(0, body.lastIndexOf("};") + 2).replace("const driverPledgeFollowup", "var driverPledgeFollowup") + "\ndriverPledgeFollowup.check();", ctx);
  return { ls, events, dialogs };
}
const root = { pathname: "/", hash: "" };
const old8 = String(Date.now() - 8 * DAY);
const pledged = at => ({ hmDriverPledgeMade: "1", hmDriverPledgedAt: at });
assert.strictEqual(run({}, root).dialogs.length, 0, "non-pledger: nothing");
assert.strictEqual(run(pledged(String(Date.now() - DAY)), root).dialogs.length, 0, "fresh pledge: nothing");
const due = run(pledged(old8), root);
assert.strictEqual(due.dialogs.length, 1, "due pledge: one dialog");
assert.deepStrictEqual(due.events, ["driver_pledge_followup_shown"]);
assert.strictEqual(due.ls.hmDriverFollowupAsks, "1");
assert.strictEqual(run(Object.assign(pledged(old8), { hmDriverFollowupDone: "1" }), root).dialogs.length, 0, "answered: nothing");
assert.strictEqual(run(Object.assign(pledged(old8), { hmDriverFollowupAsks: "2", hmDriverFollowupLast: old8 }), root).dialogs.length, 0, "2 asks used: nothing");
assert.strictEqual(run(pledged(old8), { pathname: "/de/dir/52.5,13.4/48.1,11.5", hash: "" }).dialogs.length, 0, "canonical route link: nothing");
assert.strictEqual(run(pledged(old8), { pathname: "/", hash: "#dir/52.5,13.4/48.1,11.5" }).dialogs.length, 0, "legacy #dir link: nothing");
assert.strictEqual(run(pledged(old8), root, { journey: {} }).dialogs.length, 0, "during a journey: nothing");
assert.strictEqual(run(pledged(old8), root, { dialog: {} }).dialogs.length, 0, "over another dialog: nothing");
const legacy = run({ hmDriverPledgeMade: "1" }, root);
assert.strictEqual(legacy.dialogs.length, 0, "legacy pledger stamped, not asked");
assert(Number(legacy.ls.hmDriverPledgedAt) > 0);
console.log("driver_pledge_followup behaviour ok");
