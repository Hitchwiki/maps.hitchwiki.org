# Cache-Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve `/static/*` with long-lived immutable caching and `dist/*` generated data with short `max-age` + `stale-while-revalidate`, and stop `Vary: Cookie` from fragmenting those public responses.

**Architecture:** A single `after_request` hook registered in `register_routes(app)` sets `Cache-Control`/`Vary` based on the matched endpoint (`static` vs `catch_all`), overriding the `no-cache` + `Vary: Cookie` that Werkzeug (no `max_age`) and the session layer inject. HTML routes, `sw.js`, and route JSON endpoints are left untouched.

**Tech Stack:** Flask (`hitch/__init__.py`), pytest with the existing `client` fixture (`tests/conftest.py`).

**Design doc:** `docs/superpowers/specs/2026-07-10-cache-control-design.md`

## Global Constraints

- Static assets (`/static/*`, endpoint `static`): `Cache-Control: public, max-age=31536000, immutable` and `Vary: Accept-Encoding`.
- Generated data (`dist/*`, endpoint `catch_all`): `Cache-Control: public, max-age=300, stale-while-revalidate=600` and `Vary: Accept-Encoding`.
- These two are the ONLY endpoints the hook touches. HTML (`/`, `/spot/…`, `/copyright`), `sw.js`, `favicon.ico`, `manifest.json`, and route JSON endpoints must keep their existing headers (must NOT get `max-age=31536000`).
- `Vary` on the two cached endpoints must NOT contain `Cookie`.
- The `after_request` hook must win over any `no-cache`/`Vary: Cookie` the stack injects; the pytest below is the guard (it exercises the full WSGI stack).

---

### Task 1: `after_request` cache-control hook + header tests

**Files:**
- Modify: `hitch/__init__.py` (inside `register_routes`, after the `sw` route ~line 250-255; `request` and `baseDir` are already in scope/module)
- Test: `tests/test_cache_headers.py` (create)

**Interfaces:**
- Consumes: Flask `request.endpoint`, the existing `static` and `catch_all` routes, module-level `baseDir` (`hitch/__init__.py:23`).
- Produces: `set_public_cache_headers(response)` registered via `@app.after_request` — sets `Cache-Control`/`Vary` on `static` and `catch_all` responses only.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cache_headers.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_cache_headers.py -v`
Expected: `test_static_assets_are_immutably_cached` and `test_dist_data_is_swr_cached` FAIL (current headers are `no-cache`, no `max-age`/`immutable`/`stale-while-revalidate`). `test_html_is_not_long_cached` may already pass — that's fine, it's a regression guard.

- [ ] **Step 3: Implement the hook**

In `hitch/__init__.py`, inside `register_routes(app)`, after the `sw()` route, add:

```python
    # Cache policy for public, versioned/generated files, in one place so it OVERRIDES
    # the no-cache + Vary: Cookie that Werkzeug (send_from_directory with no max_age) and
    # the session layer inject — both defeat caching of files that are safe to cache.
    # HTML, sw.js, and route endpoints are intentionally left untouched so new ?v= asset
    # links and service-worker updates keep propagating on the next load.
    @app.after_request
    def set_public_cache_headers(response):
        endpoint = request.endpoint
        if endpoint == "static":
            # ?v=<mtime> busting (asset_url) makes each URL's body immutable.
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            response.headers["Vary"] = "Accept-Encoding"
        elif endpoint == "catch_all":
            # dist/* regenerates every ~10 min and is already ~40 min stale by design, so
            # a 5-min cache + stale-while-revalidate is invisible and skips the reload
            # revalidation round-trip; ETag/Last-Modified stay for the >15-min case. These
            # files vary only by gzip vs plain, never by cookie — drop Vary: Cookie.
            response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=600"
            response.headers["Vary"] = "Accept-Encoding"
        return response
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_cache_headers.py -v`
Expected: all three PASS. If `test_dist_data_is_swr_cached`/`test_static_...` still show `Cookie` in `Vary`, the session layer is re-adding it after `after_request`; escalate — the hook may need to run last or the header force-set differently (see design doc "Risk to verify empirically").

- [ ] **Step 5: Full regression + lint**

Run: `.venv/bin/python -m pytest tests/ -q --deselect tests/test_integration.py::test_nostr_relays_have_at_least_one_ride_event`
Expected: all pass (previous baseline: 34 passed).
Run: `.venv/bin/ruff check hitch/__init__.py tests/test_cache_headers.py`
Expected: clean.

- [ ] **Step 6: Live verification against a running server**

Confirms the header values survive the real stack (test client and prod can differ in session handling) and that the `.gz` branch is unaffected.

Start (if not already running): `FLASK_APP=hitch .venv/bin/flask run --port 5001 --debug` (background).

Run and eyeball:
```
# static: immutable, no Cookie
curl -s -D - -o /dev/null http://localhost:5001/static/map.js | grep -iE "cache-control|vary"
# dist plain: SWR, no Cookie
curl -s -D - -o /dev/null http://localhost:5001/spots.json | grep -iE "cache-control|vary"
# dist gz branch: SWR + Content-Encoding: gzip + Vary: Accept-Encoding preserved
curl -s -D - -o /dev/null --compressed http://localhost:5001/spots.json | grep -iE "cache-control|vary|content-encoding"
# HTML: NOT long-cached
curl -s -D - -o /dev/null http://localhost:5001/ | grep -iE "cache-control"
```
Expected: static → `max-age=31536000, immutable`, `Vary: Accept-Encoding`. dist (both) → `max-age=300, stale-while-revalidate=600`, `Vary: Accept-Encoding`; gz request also keeps `Content-Encoding: gzip`. HTML → no `max-age=31536000`.
(If `spots.json` isn't present in dev, use any file under `dist/`, or the `_cache_test.json` approach from the test.)

- [ ] **Step 7: Commit**

```bash
git add hitch/__init__.py tests/test_cache_headers.py
git commit -m "feat(cache): immutable /static, SWR dist data, drop Vary: Cookie"
```

---

## Self-Review

- **Spec coverage:** §1 static immutable → Step 3 `static` branch + test 1. §2 dist SWR → Step 3 `catch_all` branch + test 2 (both branches covered because the hook runs on every response, incl. the gz early-return; verified in Step 6). §3 untouched HTML → test 3 guard; `sw.js`/favicon/manifest/route JSON are other endpoints the hook's `if/elif` never matches. `Vary: Cookie` removal → asserted in tests 1 & 2 and Step 6. Empirical risk → Step 4 escalation note + Step 6 live curl.
- **Placeholders:** none — all code and commands are concrete.
- **Type/name consistency:** `set_public_cache_headers`, `request.endpoint` values `"static"`/`"catch_all"`, `baseDir`, and header strings match the design doc's Global Constraints verbatim.
