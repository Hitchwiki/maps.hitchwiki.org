"""Every Umami event carries the shell it fired in (idea #195).

Read straight from the template: base.html needs a browser, and the rule under
test is a source-level contract -- the tag is added inside hmTrack, once, not at
each of the ~100 call sites.
"""

from pathlib import Path

BASE = (Path(__file__).resolve().parent.parent / "hitch" / "templates" / "base.html").read_text()


def test_hmtrack_tags_every_event_with_surface():
    assert 'window.umami.track(name, tagged(data))' in BASE
    assert "queue.push([name, tagged(data)])" in BASE
    assert 'var out = { shell: SURFACE };' in BASE


def test_surface_values_and_twa_package_referrer():
    assert '"android-app://org.hitchwiki.maps.twa"' in BASE
    for value in ('"twa"', '"pwa"', '"web"'):
        assert value in BASE


def test_shell_session_denominator_fires_once_per_tab_session():
    assert 'sessionStorage.getItem("hm_shell_seen")' in BASE
    assert 'window.hmTrack("shell_session", {})' in BASE
