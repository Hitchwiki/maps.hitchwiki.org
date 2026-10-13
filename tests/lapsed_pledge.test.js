// #821: lapsed members (last ride 180+ d ago) get one driver-pledge ask per 30 d.
const fs = require("fs"), vm = require("vm"), assert = require("assert");
const inr = fs.readFileSync(__dirname + "/../hitch/static/inride.js", "utf8");
const start = inr.indexOf("const lapsedPledge = {");
const body = inr.slice(start, inr.indexOf("// ── thinCoverageBanner", start));
assert(/setTimeout\(lapsedPledge\.check, 7000\)/.test(inr));
const DAY = 86400000;
function run(last, store, loc, extra) {
  const ls = Object.assign({}, store), events = [], dialogs = [];
  const ctx = {
    window: { HM_LAST_RIDE_AT: last },
    localStorage: { getItem: k => (k in ls ? ls[k] : null), setItem: (k, v) => { ls[k] = String(v); } },
    location: loc || { pathname: "/", hash: "" }, Date, Number, Math,
    journeyStore: { get: () => (extra && extra.journey) || null },
    journeyUI: { _openDialog: (extra && extra.dialog) || null, dialog: d => dialogs.push(d) },
    hmTrack: (n, p) => events.push([n, p.surface]), T: x => x,
  };
  vm.createContext(ctx);
  vm.runInContext(body.slice(0, body.lastIndexOf("};") + 2).replace("const lapsedPledge", "var lapsedPledge") + "\nlapsedPledge.check();", ctx);
  return { ls, events, dialogs };
}
const ago = d => new Date(Date.now() - d * DAY).toISOString();
assert.strictEqual(run("", {}).dialogs.length, 0, "no rides");
assert.strictEqual(run(ago(30), {}).dialogs.length, 0, "recent rider");
const r = run(ago(200), {});
assert.strictEqual(r.dialogs.length, 1);
assert.deepStrictEqual(r.events, [["driver_pledge_shown", "lapsed_member"]]);
r.dialogs[0].actions[0].onClick();
assert.strictEqual(r.ls.hmDriverPledgeSurface, "lapsed_member");
assert.strictEqual(run(ago(200), { hmDriverPledgeMade: "1" }).dialogs.length, 0, "already pledged");
assert.strictEqual(run(ago(200), { hmLapsedPledgeShown: String(Date.now() - 5 * DAY) }).dialogs.length, 0, "shown <30d");
assert.strictEqual(run(ago(200), {}, null, { journey: {} }).dialogs.length, 0);
assert.strictEqual(run(ago(200), {}, null, { dialog: {} }).dialogs.length, 0);
assert.strictEqual(run(ago(200), {}, { pathname: "/de/dir/52.5,13.4/48.1,11.5", hash: "" }).dialogs.length, 0);
console.log("lapsed_pledge ok");
