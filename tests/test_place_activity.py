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
