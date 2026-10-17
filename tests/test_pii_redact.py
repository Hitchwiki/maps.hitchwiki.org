from hitch.scripts.pii_redact import redact_text


def test_phone_numbers_masked():
    assert "[phone removed]" in redact_text("call me +49 170 1234567 tomorrow")
    assert "[phone removed]" in redact_text("0049-170-1234567")


def test_email_and_handle_masked():
    assert redact_text("mail a.b@example.org ok") == "mail [email removed] ok"
    assert redact_text("insta @hitch_guy99 thanks") == "insta [handle removed] thanks"


def test_ordinary_text_untouched():
    for t in ["Waited 20 min, 120 km to Berlin", "2026-10-17 11:32 ride", "Route 66 near 52.5200, 13.4050", None, ""]:
        assert redact_text(t) == t
