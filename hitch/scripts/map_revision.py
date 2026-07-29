"""Revision tokens for the database inputs consumed by ``show.py``.

The SQLite file also contains accounts, messages, notifications and other data that do
not affect the generated map. Map-input writers publish a fresh token only after their
transaction succeeds; show records the exact token it generated. Separate current and
generated tokens make a write that lands during a long generation visible to the next
run instead of being hidden by output-file mtimes.
"""

import os
import tempfile
import uuid

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DIST_DIR = os.path.join(ROOT_DIR, "dist")
CURRENT_REVISION_FILE = ".map-data-revision"
GENERATED_REVISION_FILE = ".map-data-generated-revision"


def _path(filename, dist_dir=None):
    return os.path.join(dist_dir or DIST_DIR, filename)


def _read(filename, dist_dir=None):
    try:
        with open(_path(filename, dist_dir), encoding="utf-8") as f:
            return f.read().strip() or None
    except FileNotFoundError:
        return None


def _atomic_write(filename, token, dist_dir=None):
    target_dir = dist_dir or DIST_DIR
    os.makedirs(target_dir, exist_ok=True)
    fd, temporary_path = tempfile.mkstemp(dir=target_dir, prefix=".tmp-map-revision-")
    try:
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(token)
        os.replace(temporary_path, _path(filename, target_dir))
    except Exception:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
        raise


def read_map_data_revision(dist_dir=None):
    return _read(CURRENT_REVISION_FILE, dist_dir)


def read_generated_map_revision(dist_dir=None):
    return _read(GENERATED_REVISION_FILE, dist_dir)


def mark_map_data_dirty(dist_dir=None):
    token = uuid.uuid4().hex
    _atomic_write(CURRENT_REVISION_FILE, token, dist_dir)
    return token


def mark_map_data_generated(revision, dist_dir=None):
    if revision is not None:
        _atomic_write(GENERATED_REVISION_FILE, revision, dist_dir)


def dist_dir_for_database(database_path):
    """Return the sibling ``dist`` directory for a conventional ``root/db/file`` DB."""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(database_path))), "dist")
