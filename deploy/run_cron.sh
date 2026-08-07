# Batch jobs only — the counterpart to deploy/run.sh, from the same image.
#
# Split out of the web container on 2026-08-07: cron and waitress shared one cgroup, so
# show.py's ~1.6 GB peak (and sync_fuel's ~1.9 GB) sat next to the web server, and when the
# host ran out of memory the kernel killed waitress and the site 502'd. Nothing in
# deploy/cron.sh talks to the web app, so the two have no reason to share a container.
#
# Deliberately NOT run here:
#   - `flask init`, which the web container still owns. It is create_all + roles +
#     generate-all, and running it from both containers would race on the same SQLite file
#     for no gain. docker-compose orders this container after the web one.
#
# The TypeScript Nostr fetchers that fetch_nostr / fetch_nostr_incremental shell out to are
# already built into the image by the Dockerfile, so there is no build step at start-up.
#
# The crontab itself is installed at image build time (`crontab /app/deploy/cron.sh`), so a
# change to deploy/cron.sh needs a rebuild — which a push to main does automatically.
cd /app

# Foreground, so the container's lifetime is cron's lifetime and Docker restarts it if cron
# ever dies. Job output goes to logs/*.log via the redirects in deploy/cron.sh.
exec cron -f
