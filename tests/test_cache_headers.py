import os

from hitch import baseDir


def test_static_assets_are_immutably_cached(client):
    # /static/* URLs are cache-busted with ?v=<mtime> (asset_url), so the body at a
    # given URL never changes and can be cached hard.
    resp = client.get("/static/map.js")
    assert resp.status_code == 200
    cc = resp.headers.get("Cache-Control", "")
    assert "max-age=31536000" in cc
    assert "immutable" in cc
    assert "Cookie" not in resp.headers.get("Vary", "")


def test_dist_data_is_swr_cached(client):
    # Write a throwaway file under dist/ so the test never depends on generated data.
    dist_dir = os.path.join(baseDir, "dist")
    os.makedirs(dist_dir, exist_ok=True)
    marker = os.path.join(dist_dir, "_cache_test.json")
    with open(marker, "w") as fh:
        fh.write('{"ok": true}')
    try:
        resp = client.get("/_cache_test.json")
        assert resp.status_code == 200
        cc = resp.headers.get("Cache-Control", "")
        assert "max-age=300" in cc
        assert "stale-while-revalidate=600" in cc
        assert "Cookie" not in resp.headers.get("Vary", "")
    finally:
        os.remove(marker)


def test_html_is_not_long_cached(client):
    # HTML must stay revalidate so new ?v= asset links propagate on the next load.
    resp = client.get("/copyright")
    assert resp.status_code == 200
    assert "max-age=31536000" not in resp.headers.get("Cache-Control", "")


def test_vary_cookie_preserved_on_non_cacheable_routes(client):
    # Guards against the cache-aware session interface stripping "Cookie" from
    # Vary globally instead of only on the two cacheable endpoints.
    resp = client.get("/copyright")
    assert "Cookie" in resp.headers.get("Vary", "")
