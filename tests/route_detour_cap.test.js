// #1420: alternatives() must never offer a chain that drives >4x the straight line + 150 km.
const fs = require("fs"), assert = require("assert");
const r = fs.readFileSync(__dirname + "/../hitch/static/routing.js", "utf8");
assert(/res\.carKm > 4 \* haversineKm\(start, dest\) \+ 150\) (\{ R\.lastCapped\+\+; )?continue;/.test(r));
// the cap sits inside alternatives(), after the penalty bookkeeping
const a = r.indexOf("function alternatives(");
assert(a > 0 && r.indexOf("res.carKm > 4 *", a) > a);
console.log("route_detour_cap ok");
// #1708 Check 1: gap-in-middle without gap_km says why (no-fallback / detour-capped).
assert(/R\.lastCapped = 0;/.test(r) && /props\.gap_why = !FB \? "no-fallback" : \(FB\.lastCapped \? "detour-capped" : "unknown"\)/.test(r));
// #1710: a failed one-off graph load says why, on the fallback event and on route_none.
assert(/RJ\.fallback\.err = m === "spot index mismatch" \? "mismatch"/.test(r) && /hmTrack\("route_fallback_failed"/.test(r) && /if \(!FB\) props\.fb_err = RJ\.fallback\.err/.test(r));
