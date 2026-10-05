"""One-off: introduce existing hitchhikers who are from the same city (in-app + email).

Not in cron — new arrivals are introduced live from /edit-user. Re-runnable (users who
already got the intro are skipped). Preview first:

    sudo docker exec hitchhiking-map-cron /usr/local/bin/flask --app hitch generate same_city_intro --args=--dry-run
"""

import logging
import sys

from hitch.blueprints.utils.same_city import send_same_city_intro

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
dry_run = "--dry-run" in sys.argv
notified, emailed = send_same_city_intro(dry_run=dry_run)
logging.getLogger(__name__).info("%s%d users notified, %d emailed", "[dry run] " if dry_run else "", notified, emailed)
