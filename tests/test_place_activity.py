import csv

from hitch.place_activity import COLUMNS, activity_row, write_place_activity_csv


def test_median_needs_five_recorded_waits():
    assert activity_row("Lyon", "France", 45.7578, 4.8351, [10, 20, None, float("nan"), 30])[4:] == [5, ""]
    assert activity_row("Lyon", "France", 45.7578, 4.8351, [10, 20, 30, 40, 50, None])[4:] == [6, 30]


def test_outlier_waits_are_ignored():
    assert activity_row("X", "Y", 1, 2, [10, 10, 10, 10, 10, 5000])[5] == 10


def test_csv_roundtrip(tmp_path):
    p = tmp_path / "city" / "place_activity.csv"
    write_place_activity_csv(str(p), [activity_row("Lyon", "France", 45.7578, 4.8351, [10] * 6)])
    with open(p, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0]) == COLUMNS and rows[0]["rides_90d"] == "6"


def test_activity_summary_roundtrip(tmp_path):
    from hitch.place_activity import write_activity_summary

    p = tmp_path / "activity_summary.csv"
    write_activity_summary(str(p), 258, 1100)
    with open(p, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows == [{"rides_7d": "258", "rides_28d": "1100"}]


def test_country_activity_rows_threshold_and_median():
    from hitch.place_activity import country_activity_rows

    rows = country_activity_rows({"es": [10] * 12, "fr": [5] * 9, "de": [None] * 10})
    assert rows == [["DE", 10, ""], ["ES", 12, 10]]
