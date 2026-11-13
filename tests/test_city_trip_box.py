"""IDEAS #1439: city pages carry a 'city -> destination' box that opens the planner."""
from tests.test_city_template_route_link import _render


def test_city_page_has_trip_box_with_coordinates(app):
    out = _render(app, "en")
    assert 'id="city-trip-box"' in out
    assert 'data-lat="52.52"' in out and 'data-lng="13.405"' in out
    assert "ref=city_page_trip&from=" in out


def test_trip_box_labels_translate(app):
    out = _render(app, "de")
    assert 'placeholder="Ziel"' in out and "Routenplanung" in out
