"""A shared /dir/ link must not headline a route twenty times longer than the trip.

Live 2026-09-20: Rome -> Naples (~225 km) previewed as "4,546 km in roughly 8 rides".
"""

from hitch.scripts import route_preview

ROME, NAPLES = (41.9, 12.5), (40.85, 14.27)


def _itinerary(car_km):
    leg = {"mode": "car", "from": ROME, "to": NAPLES, "via": [], "minutes": 60}
    return {"legs": [leg], "total_minutes": 60, "car_km": car_km, "num_car_legs": 1}


def _facts(monkeypatch, car_km):
    monkeypatch.setattr(route_preview, "load_router", lambda: object())
    monkeypatch.setattr(route_preview, "routes_with_fallback", lambda *a, **k: [_itinerary(car_km)])
    return route_preview.route_facts(ROME, NAPLES)


def test_a_direct_route_is_headlined(monkeypatch):
    assert _facts(monkeypatch, 260)["car_km"] == 260


def test_a_route_past_the_circuitous_ratio_is_not(monkeypatch):
    assert _facts(monkeypatch, 4546) is None


def test_the_description_falls_back_to_the_generic_card(monkeypatch):
    text = route_preview.describe(_facts(monkeypatch, 4546), "Rome", "Naples")
    assert "4,546" not in text and text.startswith("Plan a hitchhiking route")
