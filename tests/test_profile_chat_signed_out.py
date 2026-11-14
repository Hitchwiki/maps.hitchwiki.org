from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "hitch"


def test_chat_button_offered_to_signed_out_without_leaking_username():
    # IDEAS #1488
    py = (ROOT / "blueprints" / "user.py").read_text()
    line = next(ln for ln in py.splitlines() if "can_message = " in ln)
    assert "is_anonymous" not in line and "allow_messages" in line and "not is_me" in line
    html = (ROOT / "templates" / "security" / "account.html").read_text()
    ev = next(ln for ln in html.splitlines() if "profile_chat_click" in ln)
    assert "ref=profile_chat" in html
    assert "username" not in ev.split("hmTrack")[1]
