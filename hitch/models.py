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


class CoHitchhiker(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nostr_ride_event_d_tag = db.Column(db.String(255), nullable=False)
    co_hitchhiker = db.Column(db.String(255), nullable=False)
    accepted = db.Column(db.String(4), nullable=False)  # 'yes', 'no', 'open'


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
