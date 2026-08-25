"""Append-only CSV of the sign-up nudges shown after a ride is saved.

Two nudges exist, each shown at most once per browser (the client keeps the
"already seen" flag in localStorage):

* `anon-signup` — shown to someone who logged a ride while not logged in,
  offering to create an account.
* `co-hitchhiker-invite` — shown to a logged-in user who added an anonymous
  co-hitchhiker, offering to invite that person.

Only the prompt is server-side knowledge worth keeping: whether the nudge drives
sign-ups is the question, so we record which choice was made. Nothing here
identifies the visitor — no IP, no d tag — because the point is a conversion
rate, not a per-person trail.

Lives in `logs/` rather than `dist/` because `dist/` is served publicly by the
catch-all route.
"""

import csv
import os
from datetime import datetime, timezone

from hitch.helpers import dirs

SIGNUP_PROMPT_LOG_PATH = os.path.join(dirs["root"], "logs", "signup_prompts.csv")

_HEADER = ["timestamp", "prompt", "action"]

# The client is untrusted, so only known prompt/action pairs are ever recorded —
# an unknown value would just be noise in the conversion counts.
PROMPT_ACTIONS = {
    "anon-signup": {"shown", "signup", "stay-anonymous", "account-created"},
    "co-hitchhiker-invite": {"shown", "invite", "skip"},
}


def log_signup_prompt(prompt, action):
    """Record one prompt impression or button press. Never raises: logging must
    not break the (fire-and-forget) beacon request."""
    try:
        os.makedirs(os.path.dirname(SIGNUP_PROMPT_LOG_PATH), exist_ok=True)
        write_header = not os.path.exists(SIGNUP_PROMPT_LOG_PATH) or os.path.getsize(SIGNUP_PROMPT_LOG_PATH) == 0
        with open(SIGNUP_PROMPT_LOG_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(_HEADER)
            writer.writerow([datetime.now(timezone.utc).isoformat(), prompt, action])
    except Exception:
        from flask import current_app

        current_app.logger.exception("Failed to log signup prompt %s/%s", prompt, action)
