from hitch.scripts.sync_events import display_name, soonest_per_family


def test_placeholder_name_falls_back_to_page_title():
    assert display_name("Tramprennen starting point in ...", "Tramprennen 2027") == "Tramprennen 2027"
    assert display_name("Tramprennen starting point in …", "Tramprennen 2027") == "Tramprennen 2027"


def test_real_name_is_kept():
    assert display_name("Duimenrace around IJsselmeer", "Duimenrace") == "Duimenrace around IJsselmeer"


def test_one_far_future_edition_per_series():
    evs = [{"name": f"Tramprennen {y}", "start": f"{y}-08-22", "far_future": True} for y in (2029, 2027, 2028, 2030)] + [
        {"name": "Hitchgathering 2027", "start": "2027-07-20", "far_future": True}
    ]
    kept = soonest_per_family(evs)
    assert sorted(e["start"] for e in kept) == ["2027-07-20", "2027-08-22"]


def test_parse_date_drops_a_trailing_time():
    import datetime

    from hitch.scripts.sync_events import parse_date

    assert parse_date("2026-08-02 21:00") == datetime.date(2026, 8, 2)
    assert parse_date("2026-08-02T21:00:00") == datetime.date(2026, 8, 2)
    assert parse_date("2026-08-02") == datetime.date(2026, 8, 2)
    assert parse_date("not a date") is None
