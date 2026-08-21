from pathlib import Path


TEMPLATE = (Path(__file__).parents[1] / "hitch" / "templates" / "map.html").read_text()
PUBLIC_URL = "https://play.google.com/store/apps/details?id=org.hitchwiki.maps.twa"


def test_android_install_surfaces_use_the_public_listing():
    assert TEMPLATE.count(PUBLIC_URL) == 2
    assert "play.google.com/apps/testing/org.hitchwiki.maps.twa" not in TEMPLATE
    assert "testing phase" not in TEMPLATE
    assert "Android app (testing)" not in TEMPLATE


def test_both_install_surfaces_are_measurable_without_identity_data():
    assert "hmTrack('play_store_shown', { source: 'install_hint' })" in TEMPLATE
    assert "hmTrack('play_store_shown', { source: 'map_badge' })" in TEMPLATE
    assert "hmTrack('play_store_clicked', { source: 'install_hint' })" in TEMPLATE
    assert "hmTrack('play_store_clicked', { source: 'map_badge' })" in TEMPLATE


if __name__ == "__main__":
    test_android_install_surfaces_use_the_public_listing()
    test_both_install_surfaces_are_measurable_without_identity_data()
    print("play store link tests passed")
