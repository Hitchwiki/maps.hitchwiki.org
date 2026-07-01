#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Fetching latest main"
git fetch --prune origin main
git reset --hard origin/main

echo "==> Rebuilding and restarting container"
# Time the build so we can prune every cache layer it did NOT touch (see below).
build_start=$(date +%s)
sudo docker compose up -d --build
build_elapsed=$(( $(date +%s) - build_start ))

echo "==> Pruning images and build cache not used by this build"
# Old app image is now untagged (the tag moved to the freshly built one) → dangling.
sudo docker image prune -f
# Keep only the build cache this run actually used, drop everything else so we never
# hold cache that no future build will reuse. Buildkit's 'until' filter measures time
# since a layer was last used: every layer this build touched has a fresh timestamp,
# so pruning cache older than the build duration (plus a 60s safety margin so layers
# used at the very start of the build are never caught) removes exactly the untouched
# cache. '-a' also clears internal/frontend cache. This adapts automatically instead
# of a fixed age window, regardless of how often we deploy.
sudo docker builder prune -af --filter "until=$(( build_elapsed + 60 ))s"

mkdir -p logs
date -u +"%Y-%m-%dT%H:%M:%SZ commit=$(git rev-parse --short HEAD)" > logs/last_deploy.txt

echo "==> Deploy complete"
cat logs/last_deploy.txt
sudo docker ps --filter name=hitchhiking-map
