from hitch.blueprints.utils.route_demand import summarise_route_demand


def _row(day, a=(51.05, 13.73), b=(52.52, 13.40)):
    return {
        "timestamp": f"2026-10-{day:02d}T08:00:00+00:00",
        "start_lat": str(a[0]),
        "start_lon": str(a[1]),
        "dest_lat": str(b[0]),
        "dest_lon": str(b[1]),
    }


def test_corridor_needs_requests_and_distinct_days():
    rows = [_row(d) for d in (1, 2, 3, 3, 3)]
    out = summarise_route_demand(rows)
    assert out["total_requests"] == 5
    assert out["corridors"] == [{"from": [51.0, 13.5], "to": [52.5, 13.0], "requests": 5, "days": 3}]


def test_single_day_spam_is_dropped():
    out = summarise_route_demand([_row(1)] * 20)
    assert out["corridors"] == []


def test_bad_rows_and_same_cell_are_ignored():
    rows = [{"start_lat": "x"}, _row(1, (51.1, 13.6), (51.2, 13.7))]
    out = summarise_route_demand(rows)
    assert out["unparsable_rows"] == 1
    assert out["corridors"] == []


def test_no_exact_coordinates_or_names_leak():
    rows = [dict(_row(d), start_name="Home street 5") for d in (1, 2, 3, 4, 5)]
    assert "Home" not in str(summarise_route_demand(rows))


def test_filter_demand_counts_zero_match_and_hides_free_text():
    from hitch.blueprints.utils.route_demand import summarise_filter_demand

    rows = [
        {"recent": "1", "text": "secret", "matches": "0"},
        {"recent": "1", "matches": "12"},
        {"vehicle": "truck", "matches": ""},
    ]
    out = summarise_filter_demand(rows)
    assert out["total_filter_requests"] == 3
    assert {"filter": "recent", "requests": 2, "zero_match": 1} in out["filters"]
    assert "secret" not in str(out)


def _srow(day, name, lat=47.3, lon=8.5):
    return {"timestamp": f"2026-10-{day:02d}T08:00:00+00:00", "name": name, "lat": str(lat), "lon": str(lon)}


def test_search_gaps_need_picks_days_and_no_nearby_spot():
    from hitch.blueprints.utils.route_demand import summarise_search_gaps

    rows = [_srow(d, "Kusnacht, Zurich") for d in (1, 2, 3, 3, 3)]
    rows += [_srow(d, "Elsewhere", 10.1, 10.1) for d in (1, 2)]
    out = summarise_search_gaps(rows, [(50.0, 5.0)])
    assert out["gaps"] == [{"cell": [47.0, 8.5], "picks": 5, "days": 3, "label": "Kusnacht"}]
    assert "timestamp" not in str(out)
    assert summarise_search_gaps(rows, [(47.31, 8.5)])["gaps"] == []


def test_search_gap_label_drops_addresses():
    from hitch.blueprints.utils.route_demand import summarise_search_gaps

    rows = [_srow(d, "Bahnhofstr 12, X") for d in (1, 2, 3, 4, 5)]
    assert summarise_search_gaps(rows, [])["gaps"][0]["label"] is None
