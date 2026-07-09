"""Append-only CSV mapping each saved ride's Nostr d tag to the submitter's IP.

Lives in `logs/` rather than `dist/` because `dist/` is served publicly by the
catch-all route — IPs are personal data and must not be reachable over HTTP.
"""

import csv
import os
from datetime import datetime, timezone

from flask import request

from hitch.helpers import dirs

RIDE_IP_LOG_PATH = os.path.join(dirs["root"], "logs", "ride_ips.csv")

_HEADER = ["timestamp", "d_tag", "ip"]


def get_client_ip():
    """Behind the Apache/NGINX reverse proxy `remote_addr` is the proxy itself,
    so prefer the X-Real-IP header the proxy sets."""
    forwarded = request.headers.getlist("X-Real-IP")
    return forwarded[-1] if forwarded else request.remote_addr


def log_ride_ip(d_tag, ip=None):
    """Record which IP saved which ride, so a flood of fake rides can be traced
    back to its source. Never raises: a failure here must not lose the ride."""
    try:
        ip = ip or get_client_ip()
        os.makedirs(os.path.dirname(RIDE_IP_LOG_PATH), exist_ok=True)
        write_header = not os.path.exists(RIDE_IP_LOG_PATH) or os.path.getsize(RIDE_IP_LOG_PATH) == 0
        with open(RIDE_IP_LOG_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(_HEADER)
            writer.writerow([datetime.now(timezone.utc).isoformat(), d_tag, ip or ""])
    except Exception:
        from flask import current_app

        current_app.logger.exception("Failed to log ride IP for d_tag=%s", d_tag)
