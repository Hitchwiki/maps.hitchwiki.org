import os

# Set required env vars before importing the app
os.environ.setdefault("RELAYS", '["wss://relay.example.com"]')
os.environ.setdefault("NSEC", "test_key")

import pytest

from hitch import create_app
from hitch.extensions import db as _db


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
