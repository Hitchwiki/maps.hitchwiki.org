from hitch.blueprints.utils import ride_score


def test_weights_match_the_canonical_scale():
    # Guards accidental edits to the shared weights file.
    assert ride_score.WEIGHTS["driver"]["driver_reason_to_pick_up"] == 15
    assert ride_score.WEIGHTS["vehicle_base"]["vehicle_license_plate_country"] == 20
    assert sum(ride_score.WEIGHTS["driver"].values()) == 60
    assert sum(ride_score.WEIGHTS["vehicle_base"].values()) == 40
    assert {"car", "van", "camper", "taxi", "motorbike", "scooter"} == ride_score.PASSENGER_KINDS


def test_full_driver_scores_60():
    s = ride_score.score_fields(
        {
            "driver_reason_to_pick_up": ["curiosity"],
            "driver_gender": "female",
            "driver_age": 34,
            "driver_origin_country": "DE",
            "driver_languages": ["deu"],
        }
    )
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


def test_combined_pct_over_whole_pool():
    # Empty: 0 of 100 (no kind -> base-only vehicle max 40).
    empty = ride_score.score_fields({})
    assert empty["max_total"] == 100
    assert empty["pct"] == 0

    # Full driver only (60), no kind -> 60 of 100 -> 60%.
    driver_only = ride_score.score_fields(
        {
            "driver_reason_to_pick_up": ["curiosity"],
            "driver_gender": "female",
            "driver_age": 34,
            "driver_origin_country": "DE",
            "driver_languages": ["deu"],
        }
    )
    assert driver_only["max_total"] == 100
    assert driver_only["pct"] == 60

    # Everything filled on a passenger kind -> 110 of 110 -> 100%.
    full = ride_score.score_fields(
        {
            "driver_reason_to_pick_up": ["curiosity"],
            "driver_gender": "female",
            "driver_age": 34,
            "driver_origin_country": "DE",
            "driver_languages": ["deu"],
            "vehicle_kind": "car",
            "commercial": False,
            "vehicle_license_plate_country": "DE",
            "vehicle_make": "Toyota",
            "vehicle_model": "Yaris",
        }
    )
    assert full["max_total"] == 110
    assert full["pct"] == 100
