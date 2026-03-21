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