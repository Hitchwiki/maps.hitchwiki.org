import json

from hitch.blueprints.utils.wait_time_statistics import summarise_rows


def _row(wait, genders, no_ride=0):
    stops = [{"waiting_duration": f"PT{wait}M"}] if wait is not None else [{}]
    hitchhikers = [{"gender": gender} if gender is not None else {} for gender in genders]
    return json.dumps(stops), json.dumps(hitchhikers), no_ride


def test_summarises_sizes_combinations_and_exclusions():
    rows = [
        _row(10, ["female"]),
        _row(30, ["female"]),
        _row(20, ["male"]),
        _row(10, ["female", "male"]),
        _row(20, ["male", "female"]),
        _row(25, ["non_binary", None, "female"]),
        _row(40, ["male", "male", "female", "female"]),
        _row(99, ["female"], no_ride=1),
        _row(None, ["female"]),
        _row(5, ["female"] * 5),
    ]

    result = summarise_rows(rows)
    groups = {group["size"]: group for group in result["groups"]}

    assert groups[1]["median_minutes"] == 20
    assert groups[1]["rides"] == 3
    assert groups[2]["median_minutes"] == 15
    assert groups[2]["rides"] == 2
    assert groups[2]["combinations"][0]["gender_counts"] == [
        {"gender": "female", "count": 1},
        {"gender": "male", "count": 1},
    ]
    assert any(row["has_unknown"] and row["rides"] == 1 for row in groups[3]["combinations"])
    assert groups[4]["median_minutes"] == 40
    # Four recognised gender values with repetition: C(n+3, 3) combinations.
    assert [len(groups[size]["combinations"]) for size in range(1, 5)] == [4, 10, 21, 35]
    assert any(row["rides"] == 0 and row["median_minutes"] is None for row in groups[2]["combinations"])
    assert result["coverage"] == {
        "rows_read": 10,
        "rides_used": 7,
        "no_ride_excluded": 1,
        "missing_wait_or_group": 2,
    }


def test_statistics_route_renders_precomputed_data(client, monkeypatch, tmp_path):
    payload = {
        "generated_at": "2026-08-19T20:00:00Z",
        "coverage": {"rows_read": 10, "rides_used": 7},
        "groups": [
            {
                "size": 1,
                "median_minutes": 20,
                "rides": 3,
                "combinations": [
                    {
                        "gender_counts": [{"gender": "female", "count": 1}],
                        "median_minutes": 20,
                        "rides": 3,
                        "has_unknown": False,
                    }
                ],
            },
            *[{"size": size, "median_minutes": None, "rides": 0, "combinations": []} for size in range(2, 5)],
        ],
    }
    (tmp_path / "statistics.json").write_text(json.dumps(payload))
    monkeypatch.setattr("hitch.blueprints.main.get_dirs", lambda: {"dist": str(tmp_path)})

    response = client.get("/statistics/waiting-times")
    assert response.status_code == 200
    assert b"Waiting times" in response.data
    assert b"20 min" in response.data
    assert b"1 \xc3\x97 Female" in response.data

    # main_bp routes are mirrored under every supported language prefix too.
    assert client.get("/pl/statistics/waiting-times").status_code == 200
