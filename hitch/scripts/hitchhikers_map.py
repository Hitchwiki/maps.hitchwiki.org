"""Build dist/hitchhikers.json — every hitchhiker who told us where they are or are from,
as a point on the map's Hitchhikers mode. See hitch/blueprints/utils/hitchhiker_places.py
for which place is shown and why it is only ever a city centre.

Runs every 30 min (deploy/cron.sh). Steady state geocodes nothing: only a place nobody
typed before costs a Photon request, at ~1/s, capped at GEOCODE_LIMIT per run so a burst
of new profiles can't hold the lock for long.
"""

import logging

from hitch.blueprints.utils.hitchhiker_places import (
    chosen_place,
    geocode_all,
    hitchhiker_entries,
    load_cache,
    save_cache,
)
from hitch.blueprints.utils.profile_images import avatar_view, gravatar_url
from hitch.helpers import dirs, write_json_file
from hitch.models import User, UserAvatar

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

GEOCODE_LIMIT = 300

users = User.query.filter(User.active.is_(True)).order_by(User.id).all()
cache = load_cache(dirs["dist"])
places = [p[:2] for p in (chosen_place(u) for u in users) if p]
looked_up = geocode_all(places, cache, limit=GEOCODE_LIMIT)
if looked_up:
    save_cache(dirs["dist"], cache)

by_id = {u.id: u for u in users}
avatars = {}
for avatar in UserAvatar.query.all():
    user = by_id.get(avatar.user_id)
    view = avatar_view(avatar, user.email) if user else None
    if view:
        # The pin is 32 px; a 400 px Gravatar per marker is wasted bandwidth.
        avatars[avatar.user_id] = view["url"] if view["uploaded"] else gravatar_url(user.email, size=64)

entries = hitchhiker_entries(users, cache, avatars)
write_json_file(entries, "hitchhikers.json")
logger.info("%d hitchhikers on the map (%d places, %d newly geocoded)", len(entries), len(set(places)), looked_up)
