from pathlib import Path

SRC = (Path(__file__).resolve().parent.parent / "hitch/templates/ride_form.html").read_text()


def test_anon_banner_is_info_not_error_red():
    start = SRC.index('id="ride-form-anon-banner"')
    block = SRC[start : start + 900]
    assert "#dc3545" not in block
    assert "#084298" in block
