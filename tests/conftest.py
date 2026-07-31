import os

# Set required env vars before importing the app
os.environ.setdefault("RELAYS", '["wss://relay.example.com"]')
# A real (throwaway, all-0x11) nsec rather than a placeholder string: whether a ride can be
# edited or claimed depends on it being signed by *our* key (ride_sources.ride_is_replaceable),
# so a key that can't be parsed would make every ride read-only in the tests. Fixtures that
# build an owned ride must stamp it with TEST_PUBKEY.
os.environ.setdefault("NSEC", "nsec1zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zygs4rm7hz")

import pytest
from pynostr.key import PrivateKey

from hitch import create_app
from hitch.extensions import db as _db

# Derived, not hardcoded: setdefault leaves a real NSEC alone when the suite runs inside
# the container, and the fixtures still have to match whatever key is actually in use.
TEST_PUBKEY = PrivateKey.from_nsec(os.environ["NSEC"]).public_key.hex()


@pytest.fixture(scope="session")
def app():
    """Create the Flask application for the test session."""
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
    yield app
    with app.app_context():
        _db.drop_all()


@pytest.fixture
def client(app):
    """A Flask test client."""
    return app.test_client()


@pytest.fixture
def db(app):
    """Provide a clean database for each test."""
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.rollback()
