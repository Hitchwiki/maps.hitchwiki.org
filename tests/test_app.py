def test_app_creates_successfully(app):
    """The app factory creates an app with testing config."""
    assert app is not None
    assert app.config["TESTING"] is True


def test_index_returns_ok(client):
    """The main index page loads."""
    response = client.get("/")
    assert response.status_code == 200


def test_copyright_page(client):
    """The copyright page loads."""
    response = client.get("/copyright")
    assert response.status_code == 200


def test_ride_form_shows_gps_buttons(client):
    """The ride form exposes quick GPS actions for pickup/destination."""
    response = client.get("/ride")
    assert response.status_code == 200
    assert b"Use GPS" in response.data
