/* In-product feedback prompt.
 *
 * Replaces the Google Form the map used to link to from the success overlay and the
 * sign-up nudge — it drew exactly 0 responses in its lifetime against ~800 overlay
 * views/week. Instead of sending people off-site, a small free-text panel pops up
 * *inside* the app, infrequently, right after a completed action (a logged ride, a
 * finished journey). Per Till's instruction: "just let some free form feedback field
 * pop up randomly infrequently after actions in the app. Record the user or ask for
 * voluntary email if the user is anonymous."
 *
 * The note goes to POST /feedback and is stored only in the feedback_note table — never
 * Nostr, never tied to a ride. For a logged-in visitor the server snapshots the
 * username; an anonymous visitor sees an optional email field (rendered by map.html
 * only when logged out) and nothing is required.
 *
 * Self-contained: no framework. Exposes window.hmFeedback with:
 *   .open(context)        force the panel open (the "share feedback" links use this)
 *   .maybePrompt(context) open it only if the rate-limiter allows (auto-prompt)
 *
 * Rate limiting lives in localStorage (key hm_feedback_state) so "randomly infrequently"
 * survives reloads: never after the visitor has answered, never twice within 21 days,
 * a hard cap of 3 unanswered shows ever, and otherwise a 1-in-3 random roll so the
 * prompt does not appear on every single completed action.
 */
(function () {
  "use strict";

  var hmTrack = (typeof window !== "undefined" && window.hmTrack) || function () {};

  var STATE_KEY = "hm_feedback_state";
  var MIN_GAP_MS = 21 * 24 * 60 * 60 * 1000; // don't re-prompt within three weeks
  var MAX_UNANSWERED_SHOWS = 3; // stop nagging someone who keeps dismissing it
  var PROMPT_ODDS = 1 / 3; // of the actions that clear the gap, only ~1 in 3 prompts

  function readState() {
    try {
      return JSON.parse(localStorage.getItem(STATE_KEY)) || {};
    } catch (e) {
      return {};
    }
  }

  function writeState(s) {
    try {
      localStorage.setItem(STATE_KEY, JSON.stringify(s));
    } catch (e) {
      /* private mode / storage disabled — the prompt just won't rate-limit itself */
    }
  }

  function canPrompt() {
    var s = readState();
    if (s.answered) return false;
    if ((s.shownCount || 0) >= MAX_UNANSWERED_SHOWS) return false;
    if (s.lastShownMs && Date.now() - s.lastShownMs < MIN_GAP_MS) return false;
    return true;
  }

  var panel, noteEl, emailEl, thanksEl, sendBtn, skipBtn, closeBtn, currentContext;
  var wired = false;

  function els() {
    panel = document.getElementById("feedback-panel");
    if (!panel) return false;
    noteEl = document.getElementById("feedback-note");
    emailEl = document.getElementById("feedback-email"); // absent when logged in
    thanksEl = document.getElementById("feedback-thanks");
    sendBtn = document.getElementById("feedback-send");
    skipBtn = document.getElementById("feedback-skip");
    closeBtn = document.getElementById("feedback-close");
    return true;
  }

  function hide(reason) {
    if (!panel) return;
    panel.hidden = true;
    if (reason === "dismiss") {
      hmTrack("feedback_prompt_dismissed", { context: currentContext });
    }
  }

  function submit() {
    var note = (noteEl && noteEl.value || "").trim();
    if (!note) {
      if (noteEl) noteEl.focus();
      return;
    }
    var body = new URLSearchParams();
    body.set("note", note);
    body.set("context", currentContext || "manual");
    body.set("page", location.pathname);
    if (emailEl && emailEl.value.trim()) body.set("email", emailEl.value.trim());

    if (sendBtn) sendBtn.disabled = true;
    fetch("/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: body.toString(),
    })
      .then(function (r) {
        if (!r.ok) throw new Error("feedback POST " + r.status);
        var s = readState();
        s.answered = true;
        writeState(s);
        hmTrack("feedback_submitted", { context: currentContext });
        if (noteEl) noteEl.value = "";
        if (emailEl) emailEl.value = "";
        // Swap the form for a thank-you, then close on its own after a beat.
        if (noteEl) noteEl.hidden = true;
        if (emailEl) emailEl.hidden = true;
        var actions = panel.querySelector(".feedback-actions");
        if (actions) actions.hidden = true;
        if (thanksEl) thanksEl.hidden = false;
        setTimeout(function () {
          hide();
        }, 1800);
      })
      .catch(function () {
        // Network/500 — let them try again rather than silently eating the note.
        if (sendBtn) sendBtn.disabled = false;
      });
  }

  function wire() {
    if (wired || !els()) return;
    wired = true;
    if (sendBtn) sendBtn.addEventListener("click", submit);
    if (skipBtn) skipBtn.addEventListener("click", function () { hide("dismiss"); });
    if (closeBtn) closeBtn.addEventListener("click", function () { hide("dismiss"); });
  }

  function show(context) {
    if (!els()) return;
    wire();
    currentContext = context || "manual";
    // Reset any post-submit state so a second open in the same session is a fresh form.
    if (noteEl) noteEl.hidden = false;
    if (emailEl) emailEl.hidden = false;
    var actions = panel.querySelector(".feedback-actions");
    if (actions) actions.hidden = false;
    if (thanksEl) thanksEl.hidden = true;
    if (sendBtn) sendBtn.disabled = false;
    panel.hidden = false;
    if (noteEl) noteEl.focus();

    var s = readState();
    s.shownCount = (s.shownCount || 0) + 1;
    s.lastShownMs = Date.now();
    writeState(s);
    hmTrack("feedback_prompt_shown", { context: currentContext });
  }

  window.hmFeedback = {
    open: function (context) {
      show(context);
    },
    maybePrompt: function (context) {
      if (!canPrompt()) return;
      if (Math.random() >= PROMPT_ODDS) return;
      show(context);
    },
  };
})();
