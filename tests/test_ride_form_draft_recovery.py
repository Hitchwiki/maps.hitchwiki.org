from pathlib import Path

TEMPLATE = (
    Path(__file__).parents[1] / "hitch" / "templates" / "ride_form.html"
).read_text()


def test_safe_draft_is_short_lived_and_excludes_sensitive_fields():
    start = TEMPLATE.index("function safeRideFormDraftValues()")
    end = TEMPLATE.index("function safeRideFormDraftHasContent", start)
    allowlist = TEMPLATE[start:end]

    assert "24 * 60 * 60 * 1000" in TEMPLATE
    for field in ("rate", "wait", "no_ride", "signal", "reasons_to_hitchhike", "ride_reasons", "vehicle_kind"):
        assert field in allowlist
    for field in ("pickup_lat", "destination_lat", "datetime_ride", "comment", "co_hitchhiker", "license_plate", "draft_token"):
        assert field not in allowlist

    content_start = TEMPLATE.index("function safeRideFormDraftHasContent")
    content_end = TEMPLATE.index("function readSafeRideFormDraft", content_start)
    # Vehicle kind defaults to car, so it cannot alone prove that the person typed anything.
    assert "values.vehicle_kind" not in TEMPLATE[content_start:content_end]


def test_restore_is_optional_measured_and_cleared_only_after_success():
    assert "ride_form_draft_saved" in TEMPLATE
    assert "ride_form_restore_offered" in TEMPLATE
    assert "ride_form_restored_submitted" in TEMPLATE
    assert "if (json.ok === true)" in TEMPLATE
    success = TEMPLATE.index("if (json.ok === true)")
    clear = TEMPLATE.index("clearSafeRideFormDraft();", success)
    redirect = TEMPLATE.index("window.location.href = json.redirect", success)
    assert success < clear < redirect


def test_map_picker_round_trip_does_not_show_stale_restore_offer():
    assert "HM_HAS_MAP_ROUNDTRIP_DATA" in TEMPLATE
    assert "if (offered && !HM_HAS_MAP_ROUNDTRIP_DATA)" in TEMPLATE
