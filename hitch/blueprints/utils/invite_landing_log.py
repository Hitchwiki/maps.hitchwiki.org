"""Anonymous invite-link landings (#1363, maps#512).

A signed-in user's invite/share links carry `inv=<code>`, an 8-hex HMAC of their user
id under the app secret (not reversible to an id without the secret). Landings are
appended to `logs/invite_landings.csv` (not served publicly): timestamp + code + ref.
No IP, no visitor id. The sharer sees only a count for their own code.
"""

import csv
import hashlib
import hmac
import os
import re
from datetime import datetime, timezone

from hitch.helpers import dirs

INVITE_LANDINGS_LOG_PATH = os.path.join(dirs["root"], "logs", "invite_landings.csv")
INVITE_JOINS_LOG_PATH = os.path.join(dirs["root"], "logs", "invite_joins.csv")
_CODE_RE = re.compile(r"^[0-9a-f]{8}$")


def invite_code(secret_key, user_id):
    digest = hmac.new(str(secret_key).encode(), f"invite:{user_id}".encode(), hashlib.sha256).hexdigest()
    return digest[:8]


def log_invite_landing(code, ref=""):
    """Record one landing. Never raises."""
    if not _CODE_RE.match(code or ""):
        return
    try:
        os.makedirs(os.path.dirname(INVITE_LANDINGS_LOG_PATH), exist_ok=True)
        new = not os.path.exists(INVITE_LANDINGS_LOG_PATH) or os.path.getsize(INVITE_LANDINGS_LOG_PATH) == 0
        with open(INVITE_LANDINGS_LOG_PATH, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["timestamp", "code", "ref"])
            w.writerow([datetime.now(timezone.utc).isoformat(), code, re.sub(r"[^a-zA-Z0-9_-]", "", ref or "")[:64]])
    except Exception:
        from flask import current_app

        current_app.logger.exception("Failed to log invite landing")


def count_invite_landings(code):
    if not _CODE_RE.match(code or "") or not os.path.exists(INVITE_LANDINGS_LOG_PATH):
        return 0
    try:
        with open(INVITE_LANDINGS_LOG_PATH, encoding="utf-8", newline="") as f:
            return sum(1 for row in csv.DictReader(f) if row.get("code") == code)
    except Exception:
        return 0


def valid_invite_code(code):
    return bool(_CODE_RE.match(code or ""))


def log_invite_join(code):
    """Record that a brand-new account was created after landing on `?inv=<code>`. Code only, no user id. Never raises."""
    if not valid_invite_code(code):
        return
    try:
        os.makedirs(os.path.dirname(INVITE_JOINS_LOG_PATH), exist_ok=True)
        new = not os.path.exists(INVITE_JOINS_LOG_PATH) or os.path.getsize(INVITE_JOINS_LOG_PATH) == 0
        with open(INVITE_JOINS_LOG_PATH, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["timestamp", "code"])
            w.writerow([datetime.now(timezone.utc).isoformat(), code])
    except Exception:
        from flask import current_app

        current_app.logger.exception("Failed to log invite join")


def count_invite_joins(code):
    if not valid_invite_code(code) or not os.path.exists(INVITE_JOINS_LOG_PATH):
        return 0
    try:
        with open(INVITE_JOINS_LOG_PATH, encoding="utf-8", newline="") as f:
            return sum(1 for row in csv.DictReader(f) if row.get("code") == code)
    except Exception:
        return 0
