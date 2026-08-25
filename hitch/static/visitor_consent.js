/* Durable-visitor consent for the Umami tracker.
 *
 * Three tiers, in decreasing order of what we can measure:
 *
 *   granted  payload.id = a random UUID kept in localStorage. Umami derives the
 *            session id as uuid(websiteId, id), so the visitor stays the same
 *            person across months, networks and devices.
 *   default  no payload.id. Umami falls back to uuid(websiteId, ip, userAgent,
 *            monthly salt) -- what the site did before this file existed. Nothing
 *            is stored on the device, so this needs no consent.
 *   disabled localStorage["umami.disabled"], a flag the tracker itself checks.
 *            Nothing is sent at all.
 *
 * Declining costs the visitor the durable id, NOT the measurement: they fall back
 * to the middle tier. That is only honest if the prompt asks the narrow question
 * it actually asks ("recognise this browser again?") rather than a broad "do you
 * consent to analytics?" -- see the banner copy below. Getting that wrong would
 * make the middle tier a dark pattern.
 *
 * Loaded ahead of the (deferred) tracker so window.hmVisitorBeforeSend exists
 * before the tracker fires its automatic first pageview. Stamping the id in
 * before-send rather than calling identify() afterwards is what keeps that first
 * pageview in the same session as everything that follows.
 */
(function () {
  "use strict";

  var CONSENT_KEY = "hmVisitorConsent"; // "granted" | "denied"
  var ID_KEY = "hmVisitorId";
  var DISABLED_KEY = "umami.disabled"; // read by the Umami tracker itself
  // Long enough that the map has settled and the install hint (1.5 s) has had its
  // moment; short enough to still be the same visit.
  var PROMPT_DELAY_MS = 6000;

  // Every localStorage access is wrapped: Safari private mode throws on read, and
  // an analytics preference must never be able to break the page.
  function read(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (e) {
      return null;
    }
  }

  function write(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (e) {}
  }

  function remove(key) {
    try {
      window.localStorage.removeItem(key);
    } catch (e) {}
  }

  function newId() {
    try {
      if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
    } catch (e) {}
    // Not cryptographically strong, but this is a random label with no meaning
    // beyond "same browser as last time"; a collision costs one merged visitor.
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
      var r = (Math.random() * 16) | 0;
      return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
    });
  }

  function visitorId() {
    if (read(CONSENT_KEY) !== "granted") return null;
    var id = read(ID_KEY);
    if (!id) {
      id = newId();
      write(ID_KEY, id);
    }
    return id;
  }

  // The tracker calls this for every payload (data-before-send). Returning the
  // payload sends it; returning nothing drops it. It must never throw — an
  // exception here would silently stop all analytics.
  window.hmVisitorBeforeSend = function (type, payload) {
    try {
      var id = visitorId();
      if (id) payload.id = id;
    } catch (e) {}
    return payload;
  };

  // Public API, also used by the controls on /privacy.
  window.hmVisitorConsent = {
    state: function () {
      if (read(DISABLED_KEY)) return "disabled";
      return read(CONSENT_KEY) || "unset";
    },
    grant: function () {
      remove(DISABLED_KEY);
      write(CONSENT_KEY, "granted");
      // identify() also clears the tracker's cached session token, which would
      // otherwise pin this page's events to the pre-consent session.
      try {
        if (window.umami && window.umami.identify) window.umami.identify(visitorId());
      } catch (e) {}
      hide();
    },
    deny: function () {
      write(CONSENT_KEY, "denied");
      remove(ID_KEY);
      hide();
    },
    disable: function () {
      write(DISABLED_KEY, "1");
      write(CONSENT_KEY, "denied");
      remove(ID_KEY);
      hide();
    },
    enable: function () {
      remove(DISABLED_KEY);
    },
    // Forget the durable identity without turning measurement off.
    reset: function () {
      remove(CONSENT_KEY);
      remove(ID_KEY);
    },
  };

  var banner = null;

  function hide() {
    if (banner && banner.parentNode) banner.parentNode.removeChild(banner);
    banner = null;
  }

  function show() {
    if (banner || document.getElementById("hm-consent")) return;

    var style = document.createElement("style");
    // Self-contained: base.html is also the parent of the statically generated
    // city pages, which don't all load style.css.
    style.textContent =
      "#hm-consent{position:fixed;left:12px;right:12px;bottom:12px;z-index:100000;" +
      "max-width:600px;margin:0 auto;background:#fff;color:#222;border:1px solid #ccc;" +
      "border-radius:10px;box-shadow:0 6px 24px rgba(0,0,0,.18);padding:16px 18px;" +
      "font-size:.9em;line-height:1.45;padding-bottom:calc(16px + env(safe-area-inset-bottom,0px));" +
      "max-height:80vh;overflow-y:auto}" +
      "#hm-consent h2{margin:0 0 8px;font-size:1.05em}" +
      "#hm-consent p{margin:0 0 12px}" +
      "#hm-consent .hm-cat{border-top:1px solid #e5e5e5;padding:9px 0}" +
      "#hm-consent .hm-cat-head{display:flex;align-items:center;justify-content:space-between;gap:10px}" +
      "#hm-consent .hm-cat-name{font-weight:bold}" +
      "#hm-consent .hm-cat-state{font-size:.85em;color:#666;white-space:nowrap}" +
      "#hm-consent .hm-cat-desc{margin:4px 0 0;color:#555;font-size:.92em}" +
      "#hm-consent .hm-consent-actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center;" +
      "border-top:1px solid #e5e5e5;padding-top:12px;margin-top:4px}" +
      "#hm-consent button{cursor:pointer;border-radius:6px;padding:8px 15px;font-size:.95em;border:1px solid #ccc;background:#f4f4f4;color:#222}" +
      "#hm-consent button.hm-consent-yes{background:#1a73e8;border-color:#1a73e8;color:#fff}" +
      "#hm-consent a{color:#1a73e8;margin-left:auto;font-size:.9em}" +
      "@media (prefers-color-scheme:dark){#hm-consent{background:#222;color:#eee;border-color:#444}" +
      "#hm-consent .hm-cat,#hm-consent .hm-consent-actions{border-color:#3a3a3a}" +
      "#hm-consent .hm-cat-desc,#hm-consent .hm-cat-state{color:#aaa}" +
      "#hm-consent button{background:#333;border-color:#555;color:#eee}}";
    document.head.appendChild(style);

    banner = document.createElement("div");
    banner.id = "hm-consent";
    banner.setAttribute("role", "dialog");
    banner.setAttribute("aria-label", "Cookies and similar technologies");
    // The familiar two-category consent layout, but the descriptions have to stay
    // literally true. In particular the analytics row says what happens when you
    // decline: page views are still counted, storage-free. A generic "Reject" that
    // silently kept full tracking would be the dark pattern this text avoids.
    banner.innerHTML =
      "<h2>Cookies and similar technologies</h2>" +
      "<p>We use a small amount of browser storage to run the map and to understand how it is used. " +
      "Everything below stays on our own servers — no advertising, no third parties, nothing sold.</p>" +
      '<div class="hm-cat">' +
      '<div class="hm-cat-head"><span class="hm-cat-name">Essential</span>' +
      '<span class="hm-cat-state">Always active</span></div>' +
      '<p class="hm-cat-desc">Keeps you signed in and saves a ride you have started but not yet ' +
      "submitted, so it survives losing signal. The site cannot work without this.</p></div>" +
      '<div class="hm-cat">' +
      '<div class="hm-cat-head"><span class="hm-cat-name">Analytics</span>' +
      '<span class="hm-cat-state">Optional</span></div>' +
      '<p class="hm-cat-desc">Stores one random ID in your browser so we can tell a returning ' +
      "visitor from a new one, and see whether people who look up spots ever add their own rides. " +
      "It is not linked to your name, your account or your rides. " +
      "If you decline, we still count page views anonymously — but nothing is stored on your device.</p></div>" +
      '<div class="hm-consent-actions">' +
      '<button type="button" class="hm-consent-yes">Accept all</button>' +
      '<button type="button" class="hm-consent-no">Reject non-essential</button>' +
      '<a href="/privacy">Privacy policy</a>' +
      "</div>";
    document.body.appendChild(banner);

    banner.querySelector(".hm-consent-yes").addEventListener("click", function () {
      window.hmVisitorConsent.grant();
    });
    banner.querySelector(".hm-consent-no").addEventListener("click", function () {
      window.hmVisitorConsent.deny();
    });
    // "Reject" must be reachable without a mouse and dismissible like any dialog.
    banner.addEventListener("keydown", function (e) {
      if (e.key === "Escape") window.hmVisitorConsent.deny();
    });
    banner.querySelector(".hm-consent-no").focus();
  }

  function maybePrompt() {
    if (window.hmVisitorConsent.state() !== "unset") return;
    // Don't ask someone who is in the middle of something (submitting a ride,
    // logging in): the question is about analytics, and interrupting a task to
    // ask it is how banners get dismissed reflexively.
    var path = window.location.pathname;
    if (path.indexOf("/ride") === 0 || path.indexOf("/login") === 0 || path.indexOf("/report-ride") === 0) return;
    setTimeout(show, PROMPT_DELAY_MS);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", maybePrompt);
  } else {
    maybePrompt();
  }
})();
