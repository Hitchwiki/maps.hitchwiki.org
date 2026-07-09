from hitch.blueprints.utils import ride_score


def test_weights_match_the_canonical_scale():
    # Guards accidental edits to the shared weights file.
    assert ride_score.WEIGHTS["driver"]["driver_reason_to_pick_up"] == 15
    assert ride_score.WEIGHTS["vehicle_base"]["vehicle_license_plate_country"] == 20
    assert sum(ride_score.WEIGHTS["driver"].values()) == 60
    assert sum(ride_score.WEIGHTS["vehicle_base"].values()) == 40
    assert ride_score.PASSENGER_KINDS == {"car", "van", "camper", "taxi", "motorbike", "scooter"}


def test_full_driver_scores_60():
    s = ride_score.score_fields({
        "driver_reason_to_pick_up": ["curiosity"],
        "driver_gender": "female",
        "driver_age": 34,
        "driver_origin_country": "DE",
        "driver_languages": ["deu"],
    })
    assert s["driver"]["earned"] == 60
    assert s["driver"]["pct"] == 100


def test_commercial_false_is_answered_and_bus_excludes_bonus():
    s = ride_score.score_fields({"vehicle_kind": "bus", "commercial": False})
    assert s["vehicle"]["earned"] == 20
    assert s["vehicle"]["max"] == 40
    assert s["vehicle"]["bonus_eligible"] is False


def test_passenger_kind_unlocks_bonus():
    s = ride_score.score_fields({"vehicle_kind": "car", "vehicle_make": "Toyota"})
    assert s["vehicle"]["bonus_eligible"] is True
    assert s["vehicle"]["max"] == 50
    assert s["vehicle"]["earned"] == 15  # kind 10 + make 5
