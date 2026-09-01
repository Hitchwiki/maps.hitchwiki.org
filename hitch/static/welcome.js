/* First-run intro carousel.
 *
 * Shown once, right after a brand-new user's first Hitchwiki OAuth login, to explain
 * what the map is for before they land on the profile-setup form. Three slides the user
 * can swipe through or skip; either way the flow ends on /edit-user, because a new
 * account should fill in its public profile before continuing (see oauth.py, which sends
 * first-time logins here via ?welcome=1, and account.js, which opens it directly after a
 * popup login so the map never reloads).
 *
 * Self-contained: no framework, no external assets. Exposes window.HitchwikiWelcome.
 */
(function () {
  "use strict";

  // Where the flow lands once the intro is done or skipped. A fresh account still has an
  // empty public profile, so we always route to the edit form rather than the map.
  var PROFILE_URL = "/edit-user";

  var SLIDES = [
    {
      emoji: "🗺️",
      title: "Welcome to Hitchwiki Maps",
      body: "The living map of hitchhiking, built by hitchhikers. See where thousands of rides were caught — and add your own.",
    },
    {
      emoji: "📍",
      title: "Real spots, real waits",
      body: "Tap any marker for the rides logged there: where people stood, how long they waited, how it went. Plan a route and get spots that have worked before.",
    },
    {
      emoji: "✍️",
      title: "Your rides, your story",
      body: "Log every ride to build your history, stats and map. Each one you share helps the next hitchhiker on the road.",
    },
    {
      // Plain readout of an aggregate computed from our own logged rides, not advice.
      // Source: scripts/b159_driver_gender.py over the rides parquet — of 434 rides
      // that state the driver's gender, 100 are women (23.0%, 95% CI 19.3-27.2%);
      // holds up across countries and hitchhiker cohorts. See
      // research/driver-gender-2026-08-31.md. Refresh the fraction if that rerun moves.
      emoji: "🚗",
      title: "Who pulls over",
      body: "Across the rides logged on this map, about one in four drivers who stopped was a woman.",
    },
  ];

  var _open = null;

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function finish() {
    // Skip and "Set up your profile" both lead here — the intro is one-shot, so we don't
    // teardown gracefully; a full navigation is the intended exit.
    window.location.href = PROFILE_URL;
  }

  function open() {
    if (_open) return _open;

    var scrim = el("div", "welcome-scrim");
    var card = el("div", "welcome-card");
    // Taps on the card must not reach Leaflet underneath (would drop a pin / open a spot).
    if (window.L && window.L.DomEvent) window.L.DomEvent.disableClickPropagation(card);

    var skip = el("button", "welcome-skip", "Skip");
    skip.type = "button";
    skip.setAttribute("aria-label", "Skip the intro and set up your profile");
    skip.addEventListener("click", finish);
    card.appendChild(skip);

    // Horizontal scroll-snap track: native swiping on touch, and the Next button /
    // dots drive the same scrollLeft on desktop.
    var track = el("div", "welcome-track");
    track.setAttribute("role", "group");
    track.setAttribute("aria-label", "Introduction");

    SLIDES.forEach(function (s, i) {
      var slide = el("section", "welcome-slide");
      slide.setAttribute("aria-roledescription", "slide");
      slide.setAttribute("aria-label", i + 1 + " of " + SLIDES.length);

      var art = el("div", "welcome-art");
      // The dashed route + thumb is the signature: hitchhiking as a line across the map.
      art.innerHTML =
        '<svg class="welcome-route" viewBox="0 0 240 64" aria-hidden="true">' +
        '<path d="M8 52 C 60 52, 70 12, 120 12 S 180 52, 232 52" ' +
        'fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" ' +
        'stroke-dasharray="2 10"/></svg>';
      var badge = el("div", "welcome-emoji", s.emoji);
      art.appendChild(badge);
      slide.appendChild(art);

      slide.appendChild(el("h2", "welcome-title", s.title));
      slide.appendChild(el("p", "welcome-body", s.body));
      track.appendChild(slide);
    });
    card.appendChild(track);

    // Footer: dots on the left, the advancing button on the right.
    var footer = el("div", "welcome-footer");
    var dots = el("div", "welcome-dots");
    var dotEls = SLIDES.map(function (_, i) {
      var d = el("button", "welcome-dot");
      d.type = "button";
      d.setAttribute("aria-label", "Go to slide " + (i + 1));
      d.addEventListener("click", function () {
        goTo(i);
      });
      dots.appendChild(d);
      return d;
    });
    footer.appendChild(dots);

    var next = el("button", "welcome-next");
    next.type = "button";
    footer.appendChild(next);
    card.appendChild(footer);

    var current = 0;
    // The first-run carousel had no telemetry, so we could not tell how many new
    // accounts see it or how far they swipe. One dedup'd event per slide per open.
    var slideSeen = {};
    function trackSlide(i) {
      if (slideSeen[i]) return;
      slideSeen[i] = true;
      if (window.hmTrack) window.hmTrack("welcome_slide_shown", { slide: i });
    }

    function goTo(i) {
      i = Math.max(0, Math.min(SLIDES.length - 1, i));
      track.scrollTo({ left: track.clientWidth * i, behavior: "smooth" });
    }

    function render(i) {
      current = i;
      trackSlide(i);
      dotEls.forEach(function (d, di) {
        d.classList.toggle("is-active", di === i);
      });
      var last = i === SLIDES.length - 1;
      next.textContent = last ? "Set up your profile" : "Next";
      next.classList.toggle("welcome-next--cta", last);
    }

    next.addEventListener("click", function () {
      if (current === SLIDES.length - 1) finish();
      else goTo(current + 1);
    });

    // Keep the dots/button in sync with a swipe. rAF-throttled: scroll fires often.
    var ticking = false;
    track.addEventListener("scroll", function () {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(function () {
        ticking = false;
        var w = track.clientWidth || 1;
        var i = Math.round(track.scrollLeft / w);
        if (i !== current) render(i);
      });
    });

    function onKey(e) {
      if (e.key === "Escape") finish();
      else if (e.key === "ArrowRight") goTo(current + 1);
      else if (e.key === "ArrowLeft") goTo(current - 1);
    }
    document.addEventListener("keydown", onKey);

    document.body.appendChild(scrim);
    document.body.appendChild(card);
    render(0);
    // Focus the advancing button so keyboard users land inside the dialog.
    next.focus();

    function teardown() {
      document.removeEventListener("keydown", onKey);
      if (scrim.parentNode) scrim.parentNode.removeChild(scrim);
      if (card.parentNode) card.parentNode.removeChild(card);
    }
    _open = { teardown: teardown };
    return _open;
  }

  // Auto-open on the map when the OAuth callback routed a first-time user here with the
  // flag set. Strip the flag afterwards so a refresh or shared URL doesn't replay it.
  function maybeAutoOpen() {
    try {
      var params = new URLSearchParams(window.location.search);
      if (params.get("welcome") !== "1") return;
      params.delete("welcome");
      var qs = params.toString();
      var url = window.location.pathname + (qs ? "?" + qs : "") + window.location.hash;
      window.history.replaceState(null, "", url);
      open();
    } catch (e) {
      /* a missing intro is not worth surfacing an error over */
    }
  }

  window.HitchwikiWelcome = { open: open };

  if (typeof document !== "undefined") {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", maybeAutoOpen);
    else maybeAutoOpen();
  }
})();
