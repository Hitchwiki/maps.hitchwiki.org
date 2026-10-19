from pathlib import Path

THREAD = Path(__file__).resolve().parent.parent / "hitch" / "templates" / "messages" / "thread.html"


def test_thread_tracks_message_sent_without_content():
    # Requirement: measure whether "Say hello" on the hitchhiker map becomes a message, with
    # no username or text in the analytics event.
    src = THREAD.read_text()
    line = next(ln for ln in src.splitlines() if "message_sent" in ln)
    assert "hmLandingRef" in line
    assert "body" not in line and "username" not in line
    # Fires only after the POST succeeded.
    assert src.index("throw new Error('send failed')") < src.index("message_sent")
