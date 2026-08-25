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


def test_the_floating_map_badge_carries_a_visible_text_label():
    # The floating map_badge was icon-only, and measured a ~7x lower click rate
    # than the labeled install-hint banner once enough data accumulated
    # (p=0.0002, 2026-08-25) -- nobody scans an unlabeled glyph in a stack of
    # floating buttons. Pin that the badge now carries real, visible text.
    assert '<span class="play-store-btn-label">' in TEMPLATE
    label_start = TEMPLATE.index('<span class="play-store-btn-label">')
    label_end = TEMPLATE.index("</span>", label_start)
    assert TEMPLATE[label_start:label_end].strip() != '<span class="play-store-btn-label">'


if __name__ == "__main__":
    test_android_install_surfaces_use_the_public_listing()
    test_both_install_surfaces_are_measurable_without_identity_data()
    test_the_floating_map_badge_carries_a_visible_text_label()
    print("play store link tests passed")
