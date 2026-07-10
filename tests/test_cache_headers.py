import os

from hitch import baseDir


def test_busted_static_assets_are_immutably_cached(client):
    # A ?v=<mtime> URL (asset_url) can never change body under the same URL.
    resp = client.get("/static/map.js?v=123")
    assert resp.status_code == 200
    cc = resp.headers.get("Cache-Control", "")
    assert "max-age=31536000" in cc
    assert "immutable" in cc
    assert "Cookie" not in resp.headers.get("Vary", "")


def test_unbusted_static_assets_are_not_pinned(client):
    # Only map.html uses asset_url; style.css (ride_detail/report_ride/...), the marker
    # icons and countries.geojson (fetched from JS), sw.js's icon and the manifest icons
    # all arrive with no ?v=. Their bodies change across deploys under a stable URL, so
    # they must NOT be pinned for a year.
    resp = client.get("/static/map.js")
    assert resp.status_code == 200
    cc = resp.headers.get("Cache-Control", "")
    assert "max-age=31536000" not in cc
    assert "immutable" not in cc
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


def test_no_set_cookie_on_publicly_cacheable_responses(app):
    """A `public, max-age=...` response must never carry Set-Cookie.

    A shared cache/CDN could store the response together with the session cookie and
    serve one visitor's session to another. save_session emits Set-Cookie whenever the
    session is modified, and on EVERY request for a permanent session
    (SESSION_REFRESH_EACH_REQUEST defaults to True) — so this needs a live session.
    """
    dist_dir = os.path.join(baseDir, "dist")
    os.makedirs(dist_dir, exist_ok=True)
    marker = os.path.join(dist_dir, "_cookie_test.json")
    with open(marker, "w") as fh:
        fh.write('{"ok": true}')

    previous_refresh = app.config.get("SESSION_REFRESH_EACH_REQUEST")
    app.config["SESSION_REFRESH_EACH_REQUEST"] = True
    try:
        with app.test_client() as client:
            # Plant a permanent session so save_session would re-emit the cookie on
            # every subsequent request.
            with client.session_transaction() as sess:
                sess["planted"] = "1"
                sess.permanent = True

            # Sanity: a non-cacheable route DOES still set the cookie, otherwise this
            # test would pass vacuously (e.g. if sessions were disabled entirely).
            assert client.get("/copyright").headers.getlist("Set-Cookie")

            for path in ("/static/map.js", "/static/map.js?v=1", "/_cookie_test.json"):
                resp = client.get(path)
                assert resp.status_code == 200
                assert "public" in resp.headers.get("Cache-Control", "")
                assert not resp.headers.getlist("Set-Cookie"), f"Set-Cookie leaked on {path}"
    finally:
        app.config["SESSION_REFRESH_EACH_REQUEST"] = previous_refresh
        os.remove(marker)
