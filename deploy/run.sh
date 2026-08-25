# Web server only. The batch jobs run in the sibling `hitchhiking-map-cron` container,
# built from this same image — see docker-compose.yml and deploy/run_cron.sh.
#
# They used to share this container, so a cron job's memory spike was charged to the same
# cgroup as waitress: on 2026-08-07 the kernel OOM-killed waitress (826 MB RSS) while the
# host was starved, and the site 502'd. show.py alone peaks ~1.6 GB and sync_fuel ~1.9 GB,
# both far larger than the web server they were sitting next to. Separate containers mean a
# batch spike can at worst restart the batch container, never the site.
#
# The TypeScript Nostr fetchers are not built here: the Dockerfile already builds them into
# the image (`npm ci && npm run build`, identical to the `npx tsc` this used to re-run at
# boot), and only the cron container ever executes them. Dropping that step also removes a
# network call from the web container's start-up, which is dead time during every deploy.
cd /app

flask init

# Waitress, not `flask run`: Werkzeug's dev server has no bounded thread pool and no
# protection against slow or malformed clients. Apache terminates TLS and proxies here.
# 16 threads, not waitress's default 4: every map load pulls several MB of dist/ JSON
# through catch_all(), and a worker is held for the whole file read. The work is file
# I/O (releases the GIL), so threads parallelise past the 4 cores; slow clients cost
# nothing here, as waitress writes responses from its single select loop, not a worker.
#
# NOTE: url_for(_external=True) emits http:// here. The ProxyFix in create_app()
# can't fix it: waitress drops X-Forwarded-* from untrusted proxies by default
# (clear_untrusted_proxy_headers) and Caddy's container IP isn't stable enough to
# whitelist. Everything that needs an absolute https URL passes _scheme="https"
# explicitly: og:image and canonical via _external_https() in main.py, and the OAuth
# redirect_uri via _redirect_uri() in oauth.py (the consumer is registered with an
# https callback; sending http made Hitchwiki reject the authorize step).
waitress-serve --host=0.0.0.0 --port=4242 --threads=16 --call hitch:create_app