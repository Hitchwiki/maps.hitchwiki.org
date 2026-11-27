#!/usr/bin/env node
// Layout smoke test (#469, runs daily via .github/workflows/layout-smoke.yml; "catch weird-looking parts before a human does").
// Flags, per page x viewport: horizontal document overflow, text that spills out of its own
// box (the #469 case: long label in a fixed-size round button), and leaf text poking past the edge.
//   node scripts/layout_smoke.js [--base https://maps.hitchwiki.org] [path ...]   exit 1 if any finding (HTTP >=400 counts)
const path = require("path");
const { chromium } = require(path.join(__dirname, "../node_modules/playwright"));
const a = process.argv.slice(2);
const bi = a.indexOf("--base");
const base = bi >= 0 ? a.splice(bi, 2)[1] : "https://maps.hitchwiki.org";
const paths = a.length ? a : ["/", "/#success", "/#success-anon", "/#success-invite", "/statistics", "/ride", "/mitfahrbank", "/login"];
const views = [[360, 740], [390, 844], [768, 1024], [1280, 800]];
(async () => {
  const b = await chromium.launch(); let bad = 0;
  for (const p of paths) for (const [w, h] of views) {
    const pg = await b.newPage({ viewport: { width: w, height: h } });
    const go = () => pg.goto(base + p, { waitUntil: "domcontentloaded", timeout: 45000 }).catch(() => null);
    let resp = await go();
    // A deploy restart gives ~30 s of 502s (first CI run, 2026-11-27); retry twice before calling it a finding.
    for (let i = 0; i < 2 && (!resp || resp.status() >= 500); i++) { await pg.waitForTimeout(30000); resp = await go(); }
    await pg.waitForTimeout(2500);
    // Open every collapsed widget (e.g. "Show all options" lists) so hidden content gets checked too.
    for (const el of await pg.locator("button[aria-expanded=false]").all()) await el.click({ timeout: 1000 }).catch(() => {});
    await pg.waitForTimeout(300);
    const r = await pg.evaluate(() => {
      const vw = innerWidth, o = { docOverflow: document.documentElement.scrollWidth - vw, spill: [], offscreen: [] };
      for (const e of document.querySelectorAll("button,a,label,input[type=button],span,div")) {
        const s = getComputedStyle(e), rc = e.getBoundingClientRect();
        if (!rc.width || s.visibility === "hidden" || s.display === "none") continue;
        const t = e.textContent.trim().slice(0, 30);
        if (!t || e.children.length) continue;
        if (e.closest(".leaflet-map-pane")) continue; // map markers/clusters legitimately sit past the viewport edge
        if (e.scrollWidth > e.clientWidth + 2 && s.overflowX === "visible" && (e.tagName === "BUTTON" || s.borderRadius.includes("%")) && s.whiteSpace !== "normal") o.spill.push(t);
        if (e.tagName === "BUTTON" && e.scrollHeight > e.clientHeight + 2 && s.overflowY === "visible") o.spill.push(t);
        if (rc.right > vw + 2 && rc.left < vw) o.offscreen.push(t);
      }
      o.spill = [...new Set(o.spill)].slice(0, 5); o.offscreen = [...new Set(o.offscreen)].slice(0, 5);
      return o;
    }).catch(e => ({ err: e.message }));
    if (!resp || resp.status() >= 400) r.http = resp ? resp.status() : "no response";
    const flag = r.http || r.err || r.docOverflow > 2 || (r.spill && r.spill.length) || (r.offscreen && r.offscreen.length);
    if (flag) bad++;
    console.log(flag ? "FAIL" : "ok  ", p, `${w}x${h}`, flag ? JSON.stringify(r) : "");
    await pg.close();
  }
  await b.close(); process.exit(bad ? 1 : 0);
})();
