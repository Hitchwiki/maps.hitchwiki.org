from hitch.helpers import write_json_if_changed


def test_write_json_if_changed_preserves_an_unchanged_file(tmp_path):
    path = tmp_path / "spot.json"

    assert write_json_if_changed(path, {"spot": {"name": "Test"}, "rides": []}) is True
    initial_contents = path.read_text()

    assert write_json_if_changed(path, {"spot": {"name": "Test"}, "rides": []}) is False
    assert path.read_text() == initial_contents


def test_write_json_if_changed_replaces_changed_contents(tmp_path):
    path = tmp_path / "spot.json"
    path.write_text('{"spot": {}, "rides": []}')

    assert write_json_if_changed(path, {"spot": {"name": "Changed"}, "rides": []}) is True
    assert path.read_text() == '{"spot": {"name": "Changed"}, "rides": []}'
