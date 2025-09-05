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