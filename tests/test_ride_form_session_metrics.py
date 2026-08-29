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


def test_map_round_trip_is_instrumented_both_directions():
    # B435: the full-page map navigation for pickup/destination is one of the two
    # documented drains in the ~40% of new-mode sessions that never submit.
    assert "hmTrack('ride_form_map_pick_started'" in TEMPLATE
    assert "hmTrack('ride_form_returned_from_map'" in TEMPLATE

    started = TEMPLATE.index("hmTrack('ride_form_map_pick_started'")
    assert "type: type" in TEMPLATE[started : started + 200]
    assert "mode: HM_FORM_MODE" in TEMPLATE[started : started + 200]

    returned = TEMPLATE.index("hmTrack('ride_form_returned_from_map'")
    # picked: yes/no distinguishes "went to the map and came back with a point"
    # from "went and bailed".
    assert "picked: pickedCoord ? 'yes' : 'no'" in TEMPLATE[returned - 200 : returned + 200]


def test_return_event_only_fires_after_a_real_map_pick():
    # _funnel_pick_type is set only by selectLocation, so restoreFormData's own
    # _funnel_session_started write-back cannot trigger a false return event.
    assert "_funnel_pick_type: type" in TEMPLATE
    assert "if (data._funnel_pick_type) {" in TEMPLATE
