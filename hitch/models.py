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
    created_at = db.Column(db.Integer, nullable=False)

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
