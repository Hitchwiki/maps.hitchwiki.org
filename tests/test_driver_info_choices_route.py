def test_driver_info_choices_shape(client):
    resp = client.get("/driver_info_choices.json")
    assert resp.status_code == 200
    assert resp.is_json
    data = resp.get_json()
    for key in ("reasons", "genders", "languages", "countries", "plate_countries", "vehicle_kinds", "passenger_kinds"):
        assert key in data, key
    # Each choice list is a list of pairs/triples; passenger_kinds is a flat list.
    assert ["male", "Male"] in data["genders"]
    assert any(k == "car" for k, _emoji in data["vehicle_kinds"])
    assert "car" in data["passenger_kinds"]
    # commercial-eligible bonus kinds mirror the scoring weights.
    assert set(data["passenger_kinds"]) == {"car", "van", "camper", "taxi", "motorbike", "scooter"}
