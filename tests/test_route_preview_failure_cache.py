"""A route preview whose build fails must not re-run the build on every request.

Live 2026-09-20: /dir/41.9,12.5/40.85,14.27 took 25 s on 4 of 4 requests because a
failed build cached nothing and the next visit paid the timeout again.
"""

import subprocess

import pytest

from hitch.blueprints import main

START, DEST = (41.9, 12.5), (40.85, 14.27)


@pytest.fixture
def builds(app, tmp_path, monkeypatch):
    """Count subprocess builds; every one times out."""
    calls = []

    def fake_run(*args, **kwargs):
        calls.append(args)
        raise subprocess.TimeoutExpired(args[0], kwargs.get("timeout"))

    monkeypatch.setattr(main.subprocess, "run", fake_run)
    monkeypatch.setattr(main, "get_dirs", lambda: {"dist": str(tmp_path), "root": str(tmp_path)})
    return calls


def test_a_failed_build_is_not_retried_on_the_next_request(app, builds):
    with app.test_request_context("/"):
        assert main._route_preview(START, DEST)[1] is None
        assert main._route_preview(START, DEST)[1] is None
        assert main._route_preview(START, DEST)[1] is None
    assert len(builds) == 1


def test_the_failure_marker_expires(app, builds, tmp_path, monkeypatch):
    with app.test_request_context("/"):
        main._route_preview(START, DEST)
        marker = next(tmp_path.glob("dir/*.failed"))
        old = marker.stat().st_mtime - main.PREVIEW_FAILURE_TTL_S - 1
        import os

        os.utime(marker, (old, old))
        main._route_preview(START, DEST)
    assert len(builds) == 2


def test_a_success_still_serves_the_cached_preview(app, tmp_path, monkeypatch):
    monkeypatch.setattr(main, "get_dirs", lambda: {"dist": str(tmp_path), "root": str(tmp_path)})
    key = "41.90000_12.50000__40.85000_14.27000"
    (tmp_path / "dir").mkdir()
    (tmp_path / "dir" / f"{key}.json").write_text('{"km": 220}')
    with app.test_request_context("/"):
        assert main._route_preview(START, DEST) == (key, {"km": 220})
