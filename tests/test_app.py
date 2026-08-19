import re
import uuid


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


def test_ride_form_has_stable_client_id_per_render(client):
    """A rendered plain form carries one valid id across every POST from it."""
    first = client.get("/ride").get_data(as_text=True)
    second = client.get("/ride").get_data(as_text=True)

    pattern = r'name="client_d_tag" value="([^"]+)"'
    first_id = re.search(pattern, first).group(1)
    second_id = re.search(pattern, second).group(1)

    assert str(uuid.UUID(first_id)) == first_id
    assert str(uuid.UUID(second_id)) == second_id
    assert first_id != second_id
