from pathlib import Path

JS = (Path(__file__).resolve().parent.parent / "hitch" / "static" / "map.js").read_text()


def test_official_stop_sheet_names_missing_rides_858():
    assert "spot-official-no-rides" in JS
    assert "No rides logged here yet" in JS
    assert 'hmTrack("official_stop_sheet_shown"' in JS
