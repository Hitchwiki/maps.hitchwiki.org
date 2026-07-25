"""Define database tables that are created at flask init."""

from flask_security.models import fsqla_v3 as fsqla

from hitch.extensions import db

fsqla.FsModels.set_db_info(db)


class Role(db.Model, fsqla.FsRoleMixin):
    pass


class User(db.Model, fsqla.FsUserMixin):
    gender = db.Column(db.String(255), default=None)
    year_of_birth = db.Column(db.Integer, default=None)
    hitchhiking_since = db.Column(db.Integer, default=None)
    origin_country = db.Column(db.String(255), default=None)
    origin_city = db.Column(db.String(255), default=None)
    hitchwiki_username = db.Column(db.String(255), default=None)
    trustroots_username = db.Column(db.String(255), default=None)
    email_notifications = db.Column(db.Boolean, default=True, nullable=False, server_default="1")
    # Whether the one-time first-login welcome email has been sent to this user.
    # Defaults to False (incl. for users created before this column existed), so every
    # existing user also receives the welcome the first time they log in after it ships.
    welcome_email_sent = db.Column(db.Boolean, default=False, nullable=False, server_default="0")

    # Opt-in: email this user a daily digest of other registered hitchhikers whose
    # rides were logged near theirs on the same day (see notify_nearby_hitchhikers.py).
    # Privacy-sensitive (it reveals rough co-location to the recipient), so it
    # defaults to off — the user must explicitly tick the box in their profile.
    nearby_hitchhikers_email = db.Column(db.Boolean, default=False, nullable=False, server_default="0")

    # Epoch seconds of the last nearby-hitchhikers email sent to this user, or NULL if
    # never. The job runs daily over a 3-day rolling window, so the same encounter would
    # otherwise be reported up to 3 days in a row. We throttle to one email per 3 days
    # per user so they aren't notified repeatedly about the same encounter.
    nearby_hitchhikers_email_last_sent = db.Column(db.Integer, default=None)

    # Which "you signed up but haven't logged a ride yet" reminder has last been sent
    # (see remind_inactive_users.py). Stores the milestone in days: 0 = none sent,
    # 7 = the 7-day nudge sent, 30 = the final 30-day nudge sent. Advancing through the
    # stages means each user gets at most the 7-day and 30-day reminder, never a repeat;
    # once they log a ride (total_rides > 0) they're excluded and the stage stops moving.
    inactive_reminder_stage = db.Column(db.Integer, default=0, nullable=False, server_default="0")

    # Whether other registered users may open a 1:1 chat with this user and send them
    # messages. On by default so the Chat button is available across the community out of
    # the box; a user who doesn't want unsolicited messages can turn it off in their
    # profile, which also hides the Chat button and blocks anyone (incl. a reply) from
    # writing to them.
    allow_messages = db.Column(db.Boolean, default=True, nullable=False, server_default="1")

    # Whether to email this user when they receive a new chat message. Defaults to on so an
    # opted-in user doesn't miss messages, but they can turn it off independently of the
    # chat itself. Only consulted when allow_messages is on (no messages arrive otherwise).
    message_email_notifications = db.Column(db.Boolean, default=True, nullable=False, server_default="1")

    # Which unit system distances are *displayed* in ("metric" = km, "imperial" = miles).
    # Storage and every computation stay in km — this is a presentation preference only, so a
    # user switching units never rewrites ride data. Private: unlike the profile fields above
    # it is never rendered on the public profile.
    distance_unit = db.Column(db.String(16), default="metric", nullable=False, server_default="metric")

    # Lifetime hitchhiking stats, recomputed from all ride events on every show.py
    # run (not maintained on ride submission). Shown in the profile "Insights"
    # section so the page doesn't have to aggregate every ride on each load.
    total_rides = db.Column(db.Integer, default=0)
    total_distance_km = db.Column(db.Float, default=0)
    total_waiting_time_min = db.Column(db.Integer, default=0)


class Follow(db.Model):
    # Directed follow relationship between two registered users: follower_id follows
    # followed_id. A unique constraint on the pair makes a follow idempotent (a user
    # can follow another at most once) and lets us toggle on a single row.
    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    followed_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.now())

    __table_args__ = (db.UniqueConstraint("follower_id", "followed_id", name="uq_follow_follower_followed"),)


class Notification(db.Model):
    # Lightweight in-app notification shown in the user's profile. We keep only the
    # newest few per user (older rows are trimmed on insert — see utils/notifications.py),
    # so this table never grows unbounded. `kind` lets us dedupe one-off system messages
    # (e.g. the single welcome notification) without an extra per-user flag column.
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    kind = db.Column(db.String(32), nullable=False, default="general")
    message = db.Column(db.Text, nullable=False)
    # Optional in-app link the notification points to (e.g. "/create-trip"); NULL = no link.
    link = db.Column(db.String(255), nullable=True)
    is_read = db.Column(db.Boolean, nullable=False, default=False, server_default="0")
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.now())


class Message(db.Model):
    # One message in a 1:1 chat between two registered users. There is no separate
    # "conversation" row: a conversation is simply every Message where {sender, recipient}
    # equals a given unordered pair, ordered by created_at. is_read tracks whether the
    # recipient has opened the thread since it arrived (drives the unread badge and the
    # once-per-burst email throttle in the messages blueprint).
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    body = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, nullable=False, default=False, server_default="0")
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.now())


class Trip(db.Model):
    # A named collection of rides belonging to one user (e.g. "Summer 2026 Balkans").
    # Rides are attached via TripRide rows keyed on the ride's Nostr d-tag.
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    # Optional free-text blurb the user writes to describe the trip.
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.now())


class TripRide(db.Model):
    # Membership of a ride in a trip. The ride is referenced by its Nostr d-tag
    # (RideEvent.d) rather than a local row id, since rides live canonically on Nostr
    # and the local RideEvent table is fully rebuilt on every fetch. A ride can appear
    # in a trip at most once (unique pair).
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trip.id"), nullable=False)
    ride_d_tag = db.Column(db.String(255), nullable=False)

    __table_args__ = (db.UniqueConstraint("trip_id", "ride_d_tag", name="uq_trip_ride_trip_dtag"),)


class CoHitchhiker(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nostr_ride_event_d_tag = db.Column(db.String(255), nullable=False)
    co_hitchhiker = db.Column(db.String(255), nullable=False)
    accepted = db.Column(db.String(4), nullable=False)  # 'yes', 'no', 'open'


class RideReport(db.Model):
    # A logged-in user's report flagging a ride (by Nostr d-tag) as problematic.
    # One report per (ride, user): re-reporting updates the reason rather than adding a
    # new row, so a single person can never push a ride over the auto-hide threshold on
    # their own. show.py hides any ride with >= 2 reports sharing the same reason.
    id = db.Column(db.Integer, primary_key=True)
    ride_d_tag = db.Column(db.String(255), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    reason = db.Column(db.String(32), nullable=False)  # see REPORT_REASONS in report_ride.py
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.now())

    __table_args__ = (db.UniqueConstraint("ride_d_tag", "user_id", name="uq_ride_report_dtag_user"),)


class RideEvent(db.Model):
    id = db.Column(db.String(64), primary_key=True)
    kind = db.Column(db.Integer, nullable=False)
    pubkey = db.Column(db.String(64), nullable=False)
    sig = db.Column(db.String(128), nullable=False)
    content = db.Column(db.JSON, nullable=False)
    # Indexed: /pending_rides.json filters on this column on every map load, and without
    # an index that's a full scan of a 75k-row / ~130 MB table (verified via EXPLAIN QUERY
    # PLAN against prod). Creating the index on the production DB is a separate deploy
    # step (ALTER not applied by this ORM change) — see CLAUDE.md's migration section.
    created_at = db.Column(db.Integer, nullable=False, index=True)

    # Ride details as columns for easier querying
    version = db.Column(db.String(32), nullable=True)
    stops = db.Column(db.JSON, nullable=True)
    signals = db.Column(db.JSON, nullable=True)
    occupants = db.Column(db.JSON, nullable=True)
    hitchhikers = db.Column(db.JSON, nullable=True)
    declined_rides = db.Column(db.JSON, nullable=True)
    # The standard models these as a `no_ride` object and a per-occupant flag. We only need
    # the boolean answer for now: was this a "gave up, never got picked up" entry, and would
    # the hitchhiker ride with the driver again. The full detail stays in `content`/`occupants`.
    no_ride = db.Column(db.Boolean, nullable=True)
    would_ride_again = db.Column(db.Boolean, nullable=True)
    ride = db.Column(db.JSON, nullable=True)
    mode_of_transportation = db.Column(db.JSON, nullable=True)
    comment = db.Column(db.Text, nullable=True)
    rating = db.Column(db.Integer, nullable=True)
    images = db.Column(db.JSON, nullable=True)
    submission_time = db.Column(db.String(32), nullable=True)  # RFC 9557 format
    license = db.Column(db.String(255), nullable=True)
    source = db.Column(db.String(255), nullable=True)

    # Tag keys as columns
    expiration = db.Column(db.String(32), nullable=True)
    d = db.Column(db.String(255), nullable=True)
    published_at = db.Column(db.String(32), nullable=True)

    # Store all tags as JSON for flexibility
    tags = db.Column(db.JSON, nullable=True)


class OsmHitchhikingSpot(db.Model):
    id = db.Column(db.BigInteger, primary_key=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    tags = db.Column(db.JSON, nullable=True)
    timestamp = db.Column(db.String(64), nullable=True)
    user = db.Column(db.String(255), nullable=True)
    uid = db.Column(db.BigInteger, nullable=True)


class OsmCarPoolingSpot(db.Model):
    # OSM (id, type) is only globally unique together — car_pooling is often tagged on ways/relations,
    # not just nodes, so the same numeric id can collide across element types.
    id = db.Column(db.BigInteger, primary_key=True)
    osm_type = db.Column(db.String(16), primary_key=True)  # 'node', 'way', or 'relation'
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    tags = db.Column(db.JSON, nullable=True)
    timestamp = db.Column(db.String(64), nullable=True)
    user = db.Column(db.String(255), nullable=True)
    uid = db.Column(db.BigInteger, nullable=True)


class OsmFuelStationSpot(db.Model):
    # OSM (id, type) is only globally unique together — fuel stations are frequently
    # mapped as ways/relations (the forecourt area), not just nodes, so the same
    # numeric id can collide across element types. Mirrors OsmCarPoolingSpot.
    id = db.Column(db.BigInteger, primary_key=True)
    osm_type = db.Column(db.String(16), primary_key=True)  # 'node', 'way', or 'relation'
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    tags = db.Column(db.JSON, nullable=True)
    timestamp = db.Column(db.String(64), nullable=True)
    user = db.Column(db.String(255), nullable=True)
    uid = db.Column(db.BigInteger, nullable=True)


class ServiceArea(db.Model):
    # A motorway service area / gas station polygon from OSM (amenity=fuel,
    # highway=services|rest_area|service_area|parking). Built by sync_service_areas.py
    # and used by show.py to merge every spot that falls inside one polygon into a
    # single hitchhiking spot. geom_id is the OSM element id of the source feature.
    geom_id = db.Column(db.BigInteger, primary_key=True)
    name = db.Column(db.String(255), nullable=True)
    # Convex hull of the OSM geometry, serialized as WKT (shapely reads it back).
    geometry_wkt = db.Column(db.Text, nullable=False)


class RoadIsland(db.Model):
    # The patch of land enclosed by a ring of roads/slip-roads (a "road island").
    # Built by sync_road_islands.py via polygonizing the surrounding road network;
    # used by show.py to merge spots dropped around the same junction into one spot.
    id = db.Column(db.Integer, primary_key=True)
    geometry_wkt = db.Column(db.Text, nullable=False)


class HitchwikiArticleLocation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    heading = db.Column(db.String(255), nullable=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    hitchwiki_url = db.Column(db.String(255), nullable=False)


class RoutingSearch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    start_lat = db.Column(db.Float, nullable=False)
    start_lon = db.Column(db.Float, nullable=False)
    start_name = db.Column(db.String(255), nullable=True)
    end_lat = db.Column(db.Float, nullable=False)
    end_lon = db.Column(db.Float, nullable=False)
    end_name = db.Column(db.String(255), nullable=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=db.func.now())


class HitchwikiArticleMap(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    zoom = db.Column(db.Integer, nullable=False)
    hitchwiki_url = db.Column(db.String(255), nullable=False)


class RidePlace(db.Model):
    """Reverse-geocoded endpoint names for a ride, keyed by its Nostr `d` tag.

    A separate table rather than columns on RideEvent because fetch_nostr deletes and
    rebuilds ride_event wholesale every 30 minutes; place names must outlive that so the
    geocoder only ever has to resolve rides it has not seen before.

    Written offline by hitch/scripts/ride_places.py: reverse_geocoder costs ~150 MB
    resident once its index builds, which must not live in the web workers on this host.
    """

    __tablename__ = "ride_place"

    d_tag = db.Column(db.String(255), primary_key=True)
    from_place = db.Column(db.String(255), nullable=True)
    from_cc = db.Column(db.String(2), nullable=True)  # ISO 3166-1 alpha-2
    to_place = db.Column(db.String(255), nullable=True)
    to_cc = db.Column(db.String(2), nullable=True)


class SpotName(db.Model):
    """Reverse-geocoded street name for a spot, keyed by its `generate_spot_id`.

    Only the last step of the naming cascade (hitch/scripts/spot_naming.py): the spots
    that no OSM feature within 100 m can name — about 84% of them. Written offline by
    hitch/scripts/spot_names.py at one request per second against Photon, which is why
    it is cached at all rather than resolved when the spot is rendered.

    A NULL `name` means Photon answered and the place has no street or settlement, and
    is never asked again. A spot that failed to resolve has no row, so it is retried.
    """

    __tablename__ = "spot_name"

    spot_id = db.Column(db.String(64), primary_key=True)
    name = db.Column(db.String(255), nullable=True)
    latitude = db.Column("lat", db.Float, nullable=False)
    longitude = db.Column("lon", db.Float, nullable=False)
    geocoded_at = db.Column(db.String(32), nullable=False)


class DerivedRideLocation(db.Model):
    """A destination we inferred for a ride that reached Nostr without one, keyed by `d`.

    Some hitchmap.com / hitchwiki.org rides carry no destination in their `stops` yet the
    free-text comment names the city the ride actually reached ("got a lift to Kayseri").
    hitch/scripts/extract_destinations.py mines those comments (arrival-only, any transport
    mode), geocodes the city against dist/worldcities.csv, and stores the result here so it
    can be merged back onto the ride as an extra stop via to_stop().

    Kept in its own table — not written to Nostr and not columns on RideEvent — because
    fetch_nostr rebuilds ride_event wholesale every 30 min, and because this is data only
    we hold. The location is inferred from prose, never a logged GPS fix, so is_exact is
    always False: consumers should treat the coordinate as the city centre, not the spot.
    """

    __tablename__ = "derived_ride_location"

    d = db.Column(db.String(255), primary_key=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    is_exact = db.Column(db.Boolean, nullable=False, default=False)
    location_name = db.Column(db.String(255), nullable=True)
    source_comment = db.Column(db.Text, nullable=True)
    kind = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.Integer, nullable=True)

    def to_stop(self):
        # Same shape as a Nostr stop's location object so it merges straight onto a note.
        return {"location": {"latitude": self.latitude, "longitude": self.longitude, "is_exact": bool(self.is_exact)}}


class DerivedRideWait(db.Model):
    """A waiting time we inferred for a ride that reached Nostr without one, keyed by `d`.

    Many hitchmap.com / hitchwiki.org rides carry no `waiting_duration` on their first
    stop yet the free-text comment states how long the hitchhiker waited before getting
    picked up ("waited 20 min and a truck stopped"). hitch/scripts/extract_wait_times.py
    mines those comments (a cheap `\\d+ min` regex gate, then an LLM that only accepts a
    comment which actually says the writer *waited* N minutes and then got a ride — not a
    journey/drive duration) and stores the result here so it can be merged back onto the
    ride's first stop via to_iso().

    Kept in its own table — not written to Nostr and not columns on RideEvent — because
    fetch_nostr rebuilds ride_event wholesale, and because this is data only we hold. The
    minutes are inferred from prose, never a logged timer. Mirrors DerivedRideLocation.
    """

    __tablename__ = "derived_ride_wait"

    d = db.Column(db.String(255), primary_key=True)
    waiting_minutes = db.Column(db.Integer, nullable=False)
    source_comment = db.Column(db.Text, nullable=True)
    kind = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.Integer, nullable=True)

    def to_iso(self):
        # ISO 8601 duration, the same shape a Nostr stop's `waiting_duration` carries, so
        # it merges straight onto stops[0] and every wait consumer reads it unchanged.
        return f"PT{int(self.waiting_minutes)}M"


class ProposedSpot(db.Model):
    """A hitchhiking spot a user proposed by long-pressing the map.

    Unlike rides, proposed spots are NOT published to Nostr — they live only in this
    table and are drawn on the map as blue markers, so someone can flag a promising
    spot before any ride has been logged there. `comment` is a short free-text note
    from the proposer (why the spot is worth trying). Kept in its own persistent table,
    like co_hitchhiker, so the 30-minute fetch_nostr ride_event rebuild never touches it.
    Served live to the map via /proposed_spots.json (no cron / generated file), so a new
    proposal shows up immediately rather than waiting on show.py.
    """

    id = db.Column(db.Integer, primary_key=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    # Nullable: proposing does not require an account. When logged in we snapshot the
    # username (denormalised) so a later username change / account deletion still shows
    # who proposed it, matching how co_hitchhiker records store the raw name.
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    username = db.Column(db.String(255), nullable=True)
    ip = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.now())
