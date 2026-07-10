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

  function rideLabel(ride) {
    const when = (ride.created || "").slice(0, 10);
    const stars = ride.rating ? "★".repeat(ride.rating) : "";
    return { when: when, stars: stars, comment: (ride.comment || "").trim() };
  }

  // The three stats beside a ride's completion pie. A null means the ride never recorded
  // that value, so it is omitted rather than shown as a misleading "0 min" / "0 km".
  function rideStats(ride) {
    const out = [];
    const wait = ride.wait_min;
    if (wait != null) {
      out.push(wait >= 60 ? Math.floor(wait / 60) + " h " + (wait % 60) + " m" : wait + " min");
    }
    const km = ride.distance_km;
    if (km != null) out.push(Math.round(km).toLocaleString("en-US") + " km");
    return out;
  }

  function completionPct(ride) {
    const pct = ride.completion;
    return typeof pct === "number" ? Math.max(0, Math.min(100, Math.round(pct))) : 0;
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

    const rides = data.rides || [];
    body.appendChild(el("div", "acct-rides-head", ridesSummary(rides.length, data.rides_total || rides.length)));

    const list = el("ul", "acct-rides");
    rides.forEach(function (ride, idx) {
      const li = el("li", "acct-ride");
      if (idx >= RIDES_SHOWN_COLLAPSED) li.classList.add("acct-ride--hidden");

      // Completion pie: a conic-gradient sweep set from the ride's score. The number is
      // the same one the in-ride sheet's meters showed, from the canonical weights.
      const pct = completionPct(ride);
      const pie = el("span", "acct-pie");
      pie.style.setProperty("--pct", pct);
      pie.setAttribute("role", "img");
      pie.setAttribute("aria-label", pct + "% of driver and vehicle details recorded");
      pie.title = pct + "% complete";
      li.appendChild(pie);

      const meta = el("div", "acct-ride__meta");
      meta.appendChild(el("span", "acct-ride__when", rideLabel(ride).when));
      const stats = rideStats(ride);
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
  };
});
