"""The /spot/<id> page title and link preview, once spots carry a name."""

import json
import os

import pytest

from hitch.blueprints import main as main_bp

SPOT_ID = "52.30217_13.01991"


@pytest.fixture
def write_spot(app, tmp_path, monkeypatch):
    """Write a per-spot detail file into a throwaway dist/ that main.py will read."""
    monkeypatch.setattr(main_bp, "get_dirs", lambda: {"dist": str(tmp_path)})

    def _write(payload, spot_id=SPOT_ID):
        by_spot = tmp_path / "rides" / "by-spot"
        os.makedirs(by_spot, exist_ok=True)
        (by_spot / f"{spot_id}.json").write_text(json.dumps(payload))

    return _write


class TestSpotPreview:
    def test_carries_the_name_alongside_the_ratings(self, write_spot):
        write_spot({"spot": {"name": "Raststätte Michendorf-Nord", "wait": 51}, "rides": [{"rating": 4}]})
        preview = main_bp._spot_preview(SPOT_ID)
        assert preview["name"] == "Raststätte Michendorf-Nord"
        assert preview["rating"] == 4

    def test_a_named_spot_with_no_rated_ride_still_has_a_preview(self, write_spot):
        # It has no ratings to advertise, but it still deserves its name in the tab
        # title and in a messenger's link preview.
        write_spot({"spot": {"name": "Raststätte Michendorf-Nord"}, "rides": [{"comment": "nice"}]})
        preview = main_bp._spot_preview(SPOT_ID)
        assert preview["name"] == "Raststätte Michendorf-Nord"
        assert preview["rating"] is None

    def test_nothing_to_say_at_all(self, write_spot):
        write_spot({"spot": {}, "rides": [{"comment": "nice"}]})
        assert main_bp._spot_preview(SPOT_ID) is None

    def test_missing_file(self, write_spot):
        assert main_bp._spot_preview("1.00000_2.00000") is None


class TestSpotDescription:
    def test_describes_a_rated_spot(self, app, write_spot):
        write_spot({"spot": {"name": "Raststätte Michendorf-Nord", "wait": 51}, "rides": [{"rating": 4}]})
        with app.app_context():
            description = main_bp._spot_description(main_bp._spot_preview(SPOT_ID))
        assert "Rated 4.0/5 from 1 ride." in description
        assert "Typical wait 51 min." in description

    def test_no_description_without_ratings(self, write_spot):
        # A name alone is not enough to say anything about the spot, and an empty
        # description is what keeps the page noindex — see the robots meta in map.html.
        write_spot({"spot": {"name": "Raststätte Michendorf-Nord"}, "rides": []})
        assert main_bp._spot_description(main_bp._spot_preview(SPOT_ID)) is None


class TestRenderSpot:
    def test_named_spot_uses_its_name_as_the_title(self, client, write_spot):
        write_spot({"spot": {"name": "Raststätte Michendorf-Nord"}, "rides": [{"rating": 4}]})
        body = client.get(f"/spot/{SPOT_ID}").get_data(as_text=True)
        assert "Raststätte Michendorf-Nord — hitchhiking spot" in body

    def test_unnamed_spot_keeps_the_coordinate_title(self, client, write_spot):
        write_spot({"spot": {}, "rides": [{"rating": 4}]})
        body = client.get(f"/spot/{SPOT_ID}").get_data(as_text=True)
        assert "Hitchhiking spot at 52.30217, 13.01991" in body

    def test_a_named_but_unrated_spot_is_still_noindex(self, client, write_spot):
        # Naming 30k spots must not turn them into 30k indexable thin pages.
        write_spot({"spot": {"name": "An der A10, Michendorf"}, "rides": []})
        body = client.get(f"/spot/{SPOT_ID}").get_data(as_text=True)
        assert '<meta name="robots" content="noindex" />' in body
        assert "An der A10, Michendorf — hitchhiking spot" in body


class TestOnlyTheUnprefixedSpotPageIsIndexable:
    """A spot's rides are the same text in all 31 languages -- only the furniture around
    them is translated -- so the /<lang> mirrors are thin duplicates of the English page.
    Google had indexed a scattering of them (/mn/spot/45.78421_21.21907, ...)."""

    RATED = {"spot": {"name": "Raststätte Michendorf-Nord", "wait": 51}, "rides": [{"rating": 4}]}

    def test_the_mirror_is_noindex_even_when_the_spot_has_rides(self, client, write_spot):
        write_spot(self.RATED)
        assert client.get(f"/mn/spot/{SPOT_ID}").headers.get("X-Robots-Tag") == "noindex"

    def test_the_english_page_stays_indexable(self, client, write_spot):
        write_spot(self.RATED)
        response = client.get(f"/spot/{SPOT_ID}")
        assert response.headers.get("X-Robots-Tag") is None
        assert '<meta name="robots" content="noindex" />' not in response.get_data(as_text=True)

    def test_no_hreflang_cluster_around_a_noindexed_mirror(self, client, write_spot):
        # The <link rel="alternate"> block only, not the language picker's own
        # hreflang-annotated links -- those are navigation for humans.
        write_spot(self.RATED)
        body = client.get(f"/spot/{SPOT_ID}").get_data(as_text=True)
        assert '<link rel="alternate" hreflang=' not in body
