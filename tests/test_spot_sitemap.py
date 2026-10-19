import json

from hitch.blueprints.utils.spot_sitemap import sitemap_spot_ids


def _write(folder, spot_id, ratings):
    (folder / f"{spot_id}.json").write_text(json.dumps({"rides": [{"rating": r} for r in ratings]}))


def test_only_well_rated_spots_listed(tmp_path):
    _write(tmp_path, "51.1_13.7", [4, 5, 3, 4, 4, 5])
    _write(tmp_path, "52.1_13.7", [None] * 8)
    _write(tmp_path, "53.1_13.7", [4, 4])
    (tmp_path / "bad.json").write_text("{}")
    (tmp_path / "54.1_13.7.json.tmp").write_text("{}")
    assert sitemap_spot_ids(str(tmp_path)) == ["51.1_13.7"]


def test_missing_dir_is_empty(tmp_path):
    assert sitemap_spot_ids(str(tmp_path / "nope")) == []
