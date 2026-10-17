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
