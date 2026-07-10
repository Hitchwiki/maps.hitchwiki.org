// Account modal: login + profile summary without leaving the map (issue #106).
//
// Tapping the avatar used to navigate to /me, unloading the map — an in-progress ride
// lost its dock, test mode exited, and coming back re-downloaded spots.json (4.2 MB)
// and rides_index.json (26.5 MB). This renders the same essentials in a sheet instead.
//
// Dual export (browser + CommonJS) so the pure formatters are testable under node,
// matching ride_submit.js.
(function (root, factory) {
  const mod = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = mod;
  else root.AccountModal = mod;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const RIDES_SHOWN_COLLAPSED = 10;

  // ── Pure formatters (unit-tested) ──────────────────────────────────────────

  function formatInsights(insights) {
    const i = insights || {};
    const km = Math.round(i.distance_km || 0);
    const mins = Math.round(i.waiting_min || 0);
    const hours = Math.floor(mins / 60);
    return {
      rides: String(i.rides || 0),
      distance: km.toLocaleString("en-US") + " km",
      // Waiting time reads as hours once it passes an hour; minutes alone below that.
      waiting: hours > 0 ? hours + " h " + (mins % 60) + " m" : mins + " m",
      partners: String(i.partners || 0),
    };
  }

  // `shown` is what the payload carried (capped server-side); `total` is the real count.
  function ridesSummary(shown, total) {
    if (total > shown) return "Showing " + shown + " of " + total + " rides";
    return total + (total === 1 ? " ride" : " rides");
  }

  function awardsSummary(n) {
    return n + (n === 1 ? " award earned" : " awards earned");
  }

  function rideLabel(ride) {
    const when = (ride.created || "").slice(0, 10);
    const stars = ride.rating ? "★".repeat(ride.rating) : "";
    return { when: when, stars: stars, comment: (ride.comment || "").trim() };
  }

  const MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  ];

  // "2026-07-28 12:00" -> "28 - July - 26 12:00". Parsed by hand rather than with Date():
  // `created` is already the user's local submission time, and new Date("...") would
  // re-interpret it against the browser's zone and shift the day.
  function formatRideDate(created) {
    const match = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/.exec(created || "");
    if (!match) return "";
    const month = MONTHS[Number(match[2]) - 1];
    if (!month) return "";
    const stamp = match[1].slice(2) + (match[4] ? " " + match[4] + ":" + match[5] : "");
    return Number(match[3]) + " - " + month + " - " + stamp;
  }

  // What identifies a ride in the list. Place names when we have them; otherwise the
  // date, which is the only other thing that distinguishes one ride from another.
  function rideTitle(ride) {
    return rideRoute(ride) || formatRideDate(ride.created) || "Unknown ride";
  }

  // The route split into its two ends, so the row can render the destination as a real
  // element rather than a string: a missing destination is a clickable warning, and a
  // give-up is a plain statement of fact, not an error.
  //
  //   endKind "place"   -> the destination is known
  //           "missing" -> a real ride that never recorded where it ended (fixable)
  //           "gaveup"  -> never picked up; having no destination is correct
  //           null      -> nothing to say (e.g. destination unknown AND unlabelled origin)
  function routeSegments(ride) {
    const from = (ride.from_place || "").trim();
    const fromFlag = flagEmoji(ride.from_cc);
    const to = (ride.to_place || "").trim();
    const toFlag = flagEmoji(ride.to_cc);

    // With no origin name the date carries the row, and the arrow would dangle.
    const start = from ? (fromFlag ? fromFlag + " " + from : from) : formatRideDate(ride.created) || "Unknown ride";

    if (to) return { start: start, end: toFlag ? toFlag + " " + to : to, endKind: "place" };
    if (ride.gave_up) return { start: start, end: "gave up", endKind: "gaveup" };
    if (ride.missing_destination) return { start: start, end: "", endKind: "missing" };
    return { start: start, end: "", endKind: null };
  }

  // The stats beside a ride's completion pie. The date leads, then wait and distance —
  // unless the date is already serving as the ride's title, in which case repeating it
  // would just be noise.
  // A null wait/distance means the ride never recorded it, so it is omitted rather than
  // shown as a misleading "0 min" / "0 km"; a real zero still renders.
  function rideStats(ride, includeDate) {
    const out = [];
    const when = includeDate === false ? "" : (ride.created || "").slice(0, 10);
    if (when) out.push(when);
    const wait = ride.wait_min;
    if (wait != null) {
      out.push(wait >= 60 ? Math.floor(wait / 60) + " h " + (wait % 60) + " m" : wait + " min");
    }
    const km = ride.distance_km;
    if (km != null) out.push(Math.round(km).toLocaleString("en-US") + " km");
    return out;
  }

  // An ISO 3166-1 alpha-2 code as a flag emoji: the two letters map onto the regional
  // indicator symbols (U+1F1E6 is "A"). Anything that isn't two ASCII letters yields ""
  // rather than a pair of stray glyphs.
  function flagEmoji(cc) {
    const code = (cc || "").trim().toUpperCase();
    if (!/^[A-Z]{2}$/.test(code)) return "";
    return String.fromCodePoint(
      0x1f1e6 + code.charCodeAt(0) - 65,
      0x1f1e6 + code.charCodeAt(1) - 65
    );
  }

  // A ride is identified by where it went, not when it happened. Place names come from
  // the ride_place table (offline reverse geocoding); they are absent until that cron has
  // run for the ride, and a give-up has no destination — so return "" rather than
  // printing "undefined → undefined", and let rideTitle fall back to the date.
  function rideRoute(ride) {
    const from = (ride.from_place || "").trim();
    const to = (ride.to_place || "").trim();
    const fromFlag = flagEmoji(ride.from_cc);
    const toFlag = flagEmoji(ride.to_cc);
    const start = from && (fromFlag ? fromFlag + " " + from : from);
    const end = to && (toFlag ? toFlag + " " + to : to);
    if (start && end) return start + " → " + end;
    if (start) return start;
    if (end) return "→ " + end;
    return "";
  }

  function completionPct(ride) {
    const pct = ride.completion;
    return typeof pct === "number" ? Math.max(0, Math.min(100, Math.round(pct))) : 0;
  }

  // Completeness reads as a colour before it reads as a number: red is "barely logged",
  // green is done. The tiers are what drive both the pie's colour and its animation, so
  // they live here rather than being re-derived in CSS.
  function completionTier(pct) {
    if (pct >= 100) return "done";
    if (pct >= 67) return "high";
    if (pct >= 34) return "mid";
    return "low";
  }

  // How many rides are still worth topping up. Drives the nudge line above the list —
  // a concrete count is a stronger pull than a vague "add more detail".
  function ridesNeedingDetails(rides) {
    return (rides || []).filter(function (r) {
      return rideEditUrl(r) && (completionPct(r) < 100 || r.missing_destination);
    }).length;
  }

  function nudgeText(n) {
    if (n === 0) return "Every ride is fully logged. Nice.";
    return n === 1 ? "1 ride could use more detail" : n + " rides could use more detail";
  }

  // Where a ride's "fix this" CTAs point, or null when the ride isn't editable.
  // /ride?edit=<d_tag> only prefills when _user_owns_ride passes, which requires the ride
  // to have been published by us — that is exactly type "own". A ride imported from
  // another source ("own_external") or awaiting co-hitchhiker acceptance can't be edited,
  // so it gets a plain indicator instead of a dead link.
  function rideEditUrl(ride) {
    if (ride.type !== "own" || !ride.d_tag) return null;
    return "/ride?edit=" + encodeURIComponent(ride.d_tag);
  }

  // The read-only detail page for a ride. Public (main.ride_detail), so unlike editing
  // this works for every ride the list can show — imported ones and co-hitchhiker rides
  // included. A fully-logged ride has no CTA of its own; the row itself is the way in.
  function rideViewUrl(ride) {
    if (!ride.d_tag) return null;
    return "/ride/" + encodeURIComponent(ride.d_tag);
  }

  // ── DOM (browser only) ─────────────────────────────────────────────────────

  let _open = null; // { close }

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function close() {
    if (!_open) return;
    _open.teardown();
    _open = null;
  }

  function open() {
    // The account modal is a peer of the in-ride sheets, not a child: it deliberately
    // does NOT register with journeyUI._openDialog, whose single-flight guard closes the
    // parent whenever a second sheet opens.
    if (_open) return _open;

    const scrim = el("div", "inride-scrim acct-scrim");
    const sheet = el("div", "inr-sheet inr-sheet--scroll acct-sheet");

    // Taps on the sheet must never reach Leaflet underneath (would drop a pin / open a spot).
    if (window.L && window.L.DomEvent) window.L.DomEvent.disableClickPropagation(sheet);

    sheet.appendChild(el("div", "inr-sheet__grab"));
    const closeX = el("button", "inr-sheet__close");
    closeX.type = "button";
    closeX.setAttribute("aria-label", "Close");
    closeX.innerHTML = "&times;";
    closeX.addEventListener("click", close);
    sheet.appendChild(closeX);

    const body = el("div", "acct-body");
    body.appendChild(el("p", "acct-loading", "Loading…"));
    sheet.appendChild(body);

    function onKey(e) {
      if (e.key === "Escape") close();
    }
    function teardown() {
      document.removeEventListener("keydown", onKey);
      if (scrim.parentNode) scrim.parentNode.removeChild(scrim);
      if (sheet.parentNode) sheet.parentNode.removeChild(sheet);
    }

    scrim.addEventListener("click", close);
    document.addEventListener("keydown", onKey);
    document.body.appendChild(scrim);
    document.body.appendChild(sheet);
    _open = { close: close, teardown: teardown, body: body };

    refresh();
    return _open;
  }

  function refresh(needsProfile) {
    if (!_open) return;
    const body = _open.body;
    fetch("/me.json", { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        body.innerHTML = "";
        if (data && data.logged_in) renderLoggedIn(body, data, needsProfile);
        else renderLoggedOut(body);
      })
      .catch(function () {
        body.innerHTML = "";
        body.appendChild(el("p", "acct-error", "Couldn't load your account. Check your connection."));
      });
  }

  function renderLoggedOut(body) {
    body.appendChild(el("h4", null, "Your rides, saved"));
    body.appendChild(
      el("p", "acct-pitch", "Log in to track your hitchhiking, keep your ride history, and see your stats.")
    );
    const btn = el("button", "inr-big inr-big--green");
    btn.type = "button";
    btn.innerHTML = '<i class="fa-solid fa-right-to-bracket"></i> Log in with Hitchwiki';
    btn.addEventListener("click", startLogin);
    body.appendChild(btn);
  }

  function renderLoggedIn(body, data, needsProfile) {
    body.appendChild(el("h4", "acct-username", data.username));

    if (needsProfile) {
      const nudge = el("a", "acct-nudge");
      nudge.href = "/edit-user";
      nudge.textContent = "Finish setting up your profile →";
      body.appendChild(nudge);
    }

    const s = formatInsights(data.insights);
    const stats = el("div", "acct-stats");
    [
      ["Rides", s.rides],
      ["Distance", s.distance],
      ["Waiting", s.waiting],
      ["Partners", s.partners],
    ].forEach(function (pair) {
      const cell = el("div", "acct-stat");
      cell.appendChild(el("span", "acct-stat__val", pair[1]));
      cell.appendChild(el("span", "acct-stat__label", pair[0]));
      stats.appendChild(cell);
    });
    body.appendChild(stats);

    // Awards earned. Locked tiers stay on the full /insights page — the modal celebrates
    // what you have rather than nagging about what you don't.
    const awards = data.achievements || [];
    if (awards.length) {
      body.appendChild(el("div", "acct-rides-head", awardsSummary(awards.length)));
      const wrap = el("div", "acct-awards");
      awards.forEach(function (award) {
        const chip = el("span", "acct-award");
        chip.title = award.blurb || award.name;
        chip.appendChild(el("span", "acct-award__emoji", award.emoji));
        chip.appendChild(el("span", "acct-award__name", award.name));
        wrap.appendChild(chip);
      });
      body.appendChild(wrap);
    }

    const rides = data.rides || [];
    body.appendChild(el("div", "acct-rides-head", ridesSummary(rides.length, data.rides_total || rides.length)));

    // A concrete count of what's left to fill in, or a small reward when nothing is.
    const todo = ridesNeedingDetails(rides);
    const nudge = el("div", "acct-nudge-line" + (todo === 0 ? " acct-nudge-line--done" : ""));
    nudge.textContent = (todo === 0 ? "\u2728 " : "") + nudgeText(todo);
    body.appendChild(nudge);

    const list = el("ul", "acct-rides");
    rides.forEach(function (ride, idx) {
      const li = el("li", "acct-ride");
      if (idx >= RIDES_SHOWN_COLLAPSED) li.classList.add("acct-ride--hidden");

      // Every ride opens its read-only detail page — including complete ones, which have
      // no pie CTA of their own. New tab, so the map underneath is never unloaded.
      const viewUrl = rideViewUrl(ride);
      if (viewUrl) {
        li.classList.add("acct-ride--clickable");
        li.tabIndex = 0;
        li.setAttribute("role", "link");
        li.setAttribute("aria-label", "View ride details");
        const openView = function () { window.open(viewUrl, "_blank", "noopener"); };
        li.addEventListener("click", function (e) {
          // The pie and the warning are their own links to the edit form; a click on one
          // must not also open the detail page behind it.
          if (e.target.closest("a")) return;
          openView();
        });
        li.addEventListener("keydown", function (e) {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openView(); }
        });
      }

      // Completion pie: a conic-gradient sweep set from the ride's score. The number is
      // the same one the in-ride sheet's meters showed, from the canonical weights.
      // Below 100% it becomes a CTA to go fill in what's missing.
      const pct = completionPct(ride);
      const tier = completionTier(pct);
      const editUrl = rideEditUrl(ride);

      let pie;
      if (tier === "done") {
        // A finished ride stops being a progress bar and becomes a reward: the pie is
        // replaced by an award ribbon, so completing the last field visibly changes the
        // thing. The rosette is its own element because the ribbon tails are drawn with
        // the parent's ::before, and the sheen needs a second layer inside the disc.
        pie = el("span", "acct-pie acct-pie--done");
        const rosette = el("span", "acct-rosette");
        rosette.innerHTML = '<i class="fa-solid fa-check" aria-hidden="true"></i>';
        pie.appendChild(rosette);
        pie.setAttribute("role", "img");
        pie.setAttribute("aria-label", "Ride fully logged");
        pie.title = "Fully logged — nice one!";
      } else {
        const cta = Boolean(editUrl);
        pie = el(cta ? "a" : "span", "acct-pie acct-pie--" + tier + (cta ? " acct-pie--cta" : ""));
        pie.style.setProperty("--pct", pct);
        if (cta) {
          // New tab: this modal exists so the map never unloads. rel=noopener because
          // target=_blank otherwise hands the new page a window.opener reference.
          pie.href = editUrl;
          pie.target = "_blank";
          pie.rel = "noopener";
          pie.title = pct + "% complete — add driver and vehicle details";
          pie.setAttribute("aria-label", "Ride " + pct + "% complete. Add driver and vehicle details.");
        } else {
          pie.setAttribute("role", "img");
          pie.setAttribute("aria-label", pct + "% of driver and vehicle details recorded");
          pie.title = pct + "% complete";
        }
      }
      li.appendChild(pie);

      const meta = el("div", "acct-ride__meta");

      // Where it went is the ride's identity. The destination is a real element, not a
      // string, so a missing one can be a clickable warning inline in the route: the
      // arrow already promises a destination, and this is what sits where it should be.
      const seg = routeSegments(ride);
      const hasPlaces = Boolean((ride.from_place || "").trim());
      const routeEl = el("span", "acct-ride__route");
      if (!hasPlaces) routeEl.classList.add("acct-ride__route--fallback");
      routeEl.appendChild(el("span", null, seg.start));

      if (seg.endKind === "place") {
        routeEl.appendChild(el("span", "acct-ride__arrow", " → "));
        routeEl.appendChild(el("span", null, seg.end));
      } else if (seg.endKind === "gaveup") {
        // Not an error: the hitchhiker was never picked up, so there is no destination.
        routeEl.appendChild(el("span", "acct-ride__arrow", " → "));
        routeEl.appendChild(el("span", "acct-ride__gaveup", seg.end));
      } else if (seg.endKind === "missing") {
        routeEl.appendChild(el("span", "acct-ride__arrow", " → "));
        const warn = el(editUrl ? "a" : "span", "acct-ride__warn");
        warn.innerHTML = '<i class="fa-solid fa-triangle-exclamation" aria-hidden="true"></i>';
        if (editUrl) {
          warn.href = editUrl;
          warn.target = "_blank";
          warn.rel = "noopener";
          warn.title = "No destination recorded — add it";
          warn.setAttribute("aria-label", "No destination recorded for this ride. Add it.");
        } else {
          warn.title = "No destination recorded for this ride";
          warn.setAttribute("role", "img");
          warn.setAttribute("aria-label", "No destination recorded for this ride");
        }
        routeEl.appendChild(warn);
      }
      meta.appendChild(routeEl);

      // The date only appears below when it is not already carrying the row above.
      const stats = rideStats(ride, hasPlaces);
      if (stats.length) meta.appendChild(el("span", "acct-ride__stats", stats.join(" · ")));
      li.appendChild(meta);

      list.appendChild(li);
    });
    body.appendChild(list);

    if (rides.length > RIDES_SHOWN_COLLAPSED) {
      const more = el("button", "acct-more", "Show all " + rides.length);
      more.type = "button";
      more.addEventListener("click", function () {
        list.querySelectorAll(".acct-ride--hidden").forEach(function (n) {
          n.classList.remove("acct-ride--hidden");
        });
        more.remove();
      });
      body.appendChild(more);
    }

    const profile = el("a", "acct-profile-link");
    profile.href = data.profile_url || "/me";
    profile.textContent = "View full profile →";
    body.appendChild(profile);
  }

  // Login is Hitchwiki OAuth: a full-page redirect we cannot host inline. Run it in a
  // popup and let the callback postMessage the result back, so the map stays loaded.
  function startLogin() {
    const popup = window.open("/login/oauth?popup=1", "hitchwiki-login", "width=520,height=640");
    if (!popup) {
      // Popup blocked (routine on mobile Safari) — fall back to today's full-page flow.
      // The in-ride journey lives in localStorage, and the viewport is in the URL.
      window.location.href = "/login/oauth";
      return;
    }
    function onMsg(e) {
      // Trust only a message from our own origin, sent by the window we opened.
      if (e.origin !== window.location.origin) return;
      if (e.source !== popup) return;
      if (!e.data || e.data.type !== "hitchwiki-auth") return;
      window.removeEventListener("message", onMsg);
      refresh(e.data.needsProfile);
    }
    window.addEventListener("message", onMsg);
  }

  function init() {
    const link = document.querySelector("#top-account-btn a");
    if (!link) return;
    link.addEventListener("click", function (e) {
      // Let the browser handle new-tab/new-window intents and any modified click.
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
      e.preventDefault();
      open();
    });
  }

  if (typeof document !== "undefined") {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
    else init();
  }

  return {
    open: open,
    close: close,
    formatInsights: formatInsights,
    ridesSummary: ridesSummary,
    rideLabel: rideLabel,
    rideStats: rideStats,
    completionPct: completionPct,
    rideEditUrl: rideEditUrl,
    awardsSummary: awardsSummary,
    completionTier: completionTier,
    ridesNeedingDetails: ridesNeedingDetails,
    nudgeText: nudgeText,
    rideRoute: rideRoute,
    flagEmoji: flagEmoji,
    formatRideDate: formatRideDate,
    rideTitle: rideTitle,
    routeSegments: routeSegments,
    rideViewUrl: rideViewUrl,
  };
});
