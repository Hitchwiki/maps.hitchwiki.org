from hitch.blueprints.utils import ride_score


def test_weights_match_the_canonical_scale():
    # Guards accidental edits to the shared weights file.
    assert ride_score.WEIGHTS["driver"]["driver_reason_to_pick_up"] == 15
    assert ride_score.WEIGHTS["driver"]["driver_age"] == 20
    assert ride_score.WEIGHTS["vehicle_base"]["vehicle_license_plate_country"] == 20
    assert sum(ride_score.WEIGHTS["driver"].values()) == 70
    assert sum(ride_score.WEIGHTS["vehicle_base"].values()) == 30
    # make/model are no longer scored, so 100% is reachable without them.
    assert ride_score.WEIGHTS["vehicle_bonus"] == {}
    assert {"car", "van", "camper", "taxi", "motorbike", "scooter"} == ride_score.PASSENGER_KINDS


def test_full_driver_scores_70():
    s = ride_score.score_fields(
        {
            "driver_reason_to_pick_up": ["curiosity"],
            "driver_gender": "female",
            "driver_age": 34,
            "driver_origin_country": "DE",
            "driver_languages": ["deu"],
        }
    )
    assert s["driver"]["earned"] == 70
    assert s["driver"]["pct"] == 100


def test_vehicle_is_base_only_plate_and_kind():
    s = ride_score.score_fields({"vehicle_kind": "bus"})
    assert s["vehicle"]["earned"] == 10  # kind only
    assert s["vehicle"]["max"] == 30
    assert [m["field"] for m in s["vehicle"]["missing"]] == ["vehicle_license_plate_country"]


def test_make_model_never_affect_vehicle_max():
    # 100% reachable with just plate + kind; make/model are optional extras.
    s = ride_score.score_fields({"vehicle_kind": "car", "vehicle_license_plate_country": "DE"})
    assert s["vehicle"]["max"] == 30
    assert s["vehicle"]["earned"] == 30
    assert s["vehicle"]["pct"] == 100


def test_combined_pct_over_whole_pool():
    # Empty: 0 of 100.
    empty = ride_score.score_fields({})
    assert empty["max_total"] == 100
    assert empty["pct"] == 0

    # Full driver only (70), no vehicle -> 70 of 100 -> 70%.
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
    assert driver_only["pct"] == 70

    # Every scored field filled, WITHOUT make/model -> 100 of 100 -> 100%.
    full = ride_score.score_fields(
        {
            "driver_reason_to_pick_up": ["curiosity"],
            "driver_gender": "female",
            "driver_age": 34,
            "driver_origin_country": "DE",
            "driver_languages": ["deu"],
            "vehicle_kind": "car",
            "vehicle_license_plate_country": "DE",
        }
    )
    assert full["max_total"] == 100
    assert full["pct"] == 100
