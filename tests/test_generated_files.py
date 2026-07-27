import stat

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


def test_write_json_if_changed_preserves_public_file_permissions(tmp_path):
    path = tmp_path / "spot.json"

    assert write_json_if_changed(path, {"rides": []}) is True
    assert stat.S_IMODE(path.stat().st_mode) == 0o644

    path.chmod(0o664)
    assert write_json_if_changed(path, {"rides": [1]}) is True
    assert stat.S_IMODE(path.stat().st_mode) == 0o664
