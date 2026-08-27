from hitch.scripts.map_revision import (
    mark_map_data_dirty,
    mark_map_data_generated,
    read_generated_map_revision,
    read_map_data_revision,
)


def test_dirty_and_generated_revisions_are_tracked_separately(tmp_path):
    assert read_map_data_revision(tmp_path) is None
    assert read_generated_map_revision(tmp_path) is None

    first = mark_map_data_dirty(tmp_path)
    mark_map_data_generated(first, tmp_path)
    assert read_map_data_revision(tmp_path) == first
    assert read_generated_map_revision(tmp_path) == first

    second = mark_map_data_dirty(tmp_path)
    assert second != first
    assert read_map_data_revision(tmp_path) == second
    assert read_generated_map_revision(tmp_path) == first
