// Web Push opt-in, shown on the ride-saved screen to signed-in riders (#292 slice 1).
//
// Two steps on purpose: an in-page "Yes, notify me" button first, and only that click
// triggers the browser's own permission prompt. A browser prompt that is refused is
// remembered for good, so it must never fire cold. Notifications are limited to alerts
// the app already shows in the profile (new follower, message, comment on a ride).
//
// Dual export (browser + CommonJS) so the pure helper is testable under node.
(function (root, factory) {
  const mod = factory(root);
  if (typeof module !== "undefined" && module.exports) module.exports = mod;
  else root.HmPushOptin = mod;
})(typeof self !== "undefined" ? self : this, function (root) {
  "use strict";

  const DECLINED_KEY = "hmPushDeclined";

  // PushManager.subscribe wants the VAPID key as bytes; the server hands it over as URL-safe base64.
  function urlBase64ToUint8Array(b64) {
    const pad = "=".repeat((4 - (b64.length % 4)) % 4);
    const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
    return Uint8Array.from(raw, (c) => c.charCodeAt(0));
  }

  function track(name, data) {
    if (root.hmTrack) root.hmTrack(name, data || {});
  }

  // Everything the prompt needs, or null when it must stay hidden.
  function supported() {
    return (
      typeof navigator !== "undefined" &&
      "serviceWorker" in navigator &&
      typeof root.PushManager !== "undefined" &&
      typeof root.Notification !== "undefined" &&
      root.Notification.permission === "default"
    );
  }

  async function subscribe(note) {
    const t = root.tr || ((s) => s);
    track("push_optin_clicked");
    try {
      const permission = await root.Notification.requestPermission();
      if (permission !== "granted") {
        track("push_permission_denied");
        note.style.display = "none";
        return;
      }
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(note.dataset.vapidKey),
      });
      const res = await fetch("/push/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(sub.toJSON()),
      });
      track(res.ok ? "push_subscribed" : "push_subscribe_failed");
      note.textContent = res.ok ? t("Done. You'll get a notification when something happens on your profile.") : "";
      if (!res.ok) note.style.display = "none";
    } catch (e) {
      track("push_subscribe_failed");
      note.style.display = "none";
    }
  }

  function render() {
    const note = root.document && root.document.getElementById("success-push-optin");
    if (!note) return; // not signed in, or the server has no VAPID key
    note.style.display = "none";
    if (!supported() || localStorage.getItem(DECLINED_KEY)) return;
    const t = root.tr || ((s) => s);
    note.textContent = "";
    note.append(
      t("Want a phone notification when someone follows you, writes to you or comments on your ride? "),
    );
    const yes = root.document.createElement("a");
    yes.href = "#";
    yes.textContent = t("Yes, notify me");
    yes.addEventListener("click", (e) => {
      e.preventDefault();
      subscribe(note);
    });
    const no = root.document.createElement("a");
    no.href = "#";
    no.textContent = t("No thanks");
    no.addEventListener("click", (e) => {
      e.preventDefault();
      localStorage.setItem(DECLINED_KEY, "1");
      track("push_optin_declined");
      note.style.display = "none";
    });
    note.append(yes, " · ", no);
    note.style.display = "block";
    track("push_optin_shown");
  }

  return { render, urlBase64ToUint8Array };
});
