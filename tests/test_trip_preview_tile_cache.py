"""_fetch_tile (hitch/blueprints/user.py), the OSM tile fetcher behind trip preview
images (/trip/<id>/preview.png), used to hit tile.openstreetmap.org live on every
request with no disk cache at all -- unlike /dir/'s link previews (route_preview.py),
which OSM's own tile-usage policy required a cache for from the start. A trip
preview gets refetched by every messenger's link-unfurl crawler each time it's
shared, so the same tiles get requested repeatedly with nothing to show for it.
This ports route_preview.py's dist/tiles/<z>/<x>/<y>.png cache onto the same
function -- same layout, so it shares hits with /dir/'s cache for free.
"""

import os

from hitch.blueprints import user as user_module


class _FakeResponse:
    def __init__(self, content, status_code=200):
        self.content = content
        self.status_code = status_code


def test_fetch_tile_writes_then_reads_from_the_disk_cache(monkeypatch, tmp_path):
    calls = []

    def fake_get(url, timeout, headers):
        calls.append(url)
        # A minimal real PNG (1x1 white pixel) so PIL can decode it.
        return _FakeResponse(
            bytes.fromhex(
                "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
                "53de0000000c4944415408d763f8ffff3f0005fe02fea16dcf8f0000000049454e44ae426082"
            )
        )

    monkeypatch.setattr(user_module, "requests", type("R", (), {"get": staticmethod(fake_get)}))
    monkeypatch.setattr(user_module, "get_dirs", lambda: {"dist": str(tmp_path)})

    img1 = user_module._fetch_tile(5, 3, 4)
    assert img1 is not None
    assert len(calls) == 1

    cache_path = tmp_path / "tiles" / "5" / "3" / "4.png"
    assert cache_path.is_file(), "tile was not written to the shared dist/tiles/ cache"

    # Second fetch for the same tile must come from disk, not the network again.
    img2 = user_module._fetch_tile(5, 3, 4)
    assert img2 is not None
    assert len(calls) == 1, "cache hit re-fetched from the network instead of reading disk"


def test_fetch_tile_bumps_mtime_on_a_cache_hit(monkeypatch, tmp_path):
    def fake_get(url, timeout, headers):
        return _FakeResponse(
            bytes.fromhex(
                "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
                "53de0000000c4944415408d763f8ffff3f0005fe02fea16dcf8f0000000049454e44ae426082"
            )
        )

    monkeypatch.setattr(user_module, "requests", type("R", (), {"get": staticmethod(fake_get)}))
    monkeypatch.setattr(user_module, "get_dirs", lambda: {"dist": str(tmp_path)})

    user_module._fetch_tile(5, 3, 4)
    cache_path = tmp_path / "tiles" / "5" / "3" / "4.png"
    old_mtime = cache_path.stat().st_mtime
    os.utime(cache_path, (old_mtime - 1000, old_mtime - 1000))
    aged_mtime = cache_path.stat().st_mtime

    user_module._fetch_tile(5, 3, 4)
    assert cache_path.stat().st_mtime > aged_mtime, (
        "cron.sh's age-based prune reads mtime as 'last used' -- a tile still in "
        "rotation must not age out just because it was fetched a while ago"
    )


def test_fetch_tile_returns_none_on_a_non_200_without_caching_anything(monkeypatch, tmp_path):
    def fake_get(url, timeout, headers):
        return _FakeResponse(b"", status_code=404)

    monkeypatch.setattr(user_module, "requests", type("R", (), {"get": staticmethod(fake_get)}))
    monkeypatch.setattr(user_module, "get_dirs", lambda: {"dist": str(tmp_path)})

    result = user_module._fetch_tile(5, 3, 4)
    assert result is None
    assert not (tmp_path / "tiles" / "5" / "3" / "4.png").exists()
