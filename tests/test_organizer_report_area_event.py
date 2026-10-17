from pathlib import Path

JS = Path(__file__).resolve().parent.parent / "hitch" / "static" / "organizers.js"


def test_report_viewed_event_carries_coarse_area():
    # Requirement: tell mailed towns apart in analytics without precise coordinates.
    src = JS.read_text()
    assert "track('organizer_report_viewed', {area:" in src
    assert "toFixed(1)" in src
