import gzip
import json
import os

from hitch import helpers


def test_write_json_file_leaves_complete_pair_and_no_temp_files(tmp_path, monkeypatch):
    monkeypatch.setitem(helpers.dirs, "dist", str(tmp_path))
    helpers.write_json_file({"a": [1, 2]}, "x.json")

    assert sorted(os.listdir(tmp_path)) == ["x.json", "x.json.gz"]
    assert json.loads((tmp_path / "x.json").read_text()) == {"a": [1, 2]}
    assert json.loads(gzip.decompress((tmp_path / "x.json.gz").read_bytes())) == {"a": [1, 2]}
    # The route refuses a sidecar older than the plain file it encodes.
    assert os.path.getmtime(tmp_path / "x.json.gz") >= os.path.getmtime(tmp_path / "x.json")
