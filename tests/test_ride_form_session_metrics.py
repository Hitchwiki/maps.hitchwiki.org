from pathlib import Path


TEMPLATE = (
    Path(__file__).parents[1] / "hitch" / "templates" / "ride_form.html"
).read_text()


def test_session_start_is_deduplicated_across_location_round_trips():
    assert "HM_FORM_SESSION_STARTED = !!hmDraft._funnel_session_started" in TEMPLATE
    assert "if (!HM_FORM_SESSION_STARTED)" in TEMPLATE
    assert "hmTrack('ride_form_session_started'" in TEMPLATE
    assert "_funnel_session_started: HM_FORM_SESSION_STARTED" in TEMPLATE


def test_session_funnel_keeps_mode_on_both_stages():
    start = TEMPLATE.index("hmTrack('ride_form_session_started'")
    submit = TEMPLATE.index("hmTrack('ride_form_session_submitted'")
    assert "mode: HM_FORM_MODE" in TEMPLATE[start : start + 250]
    assert "mode: HM_FORM_MODE" in TEMPLATE[submit : submit + 250]


def test_legacy_render_event_remains_for_historical_series():
    assert "hmTrack('ride_form_started'" in TEMPLATE
    assert "hmTrack('ride_form_submitted'" in TEMPLATE
