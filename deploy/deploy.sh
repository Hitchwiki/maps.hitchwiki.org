#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Fetching latest main"
git fetch --prune origin main
git reset --hard origin/main

echo "==> Rebuilding and restarting container"
sudo docker compose up -d --build

echo "==> Pruning dangling images and stale build cache"
sudo docker image prune -f
# Build cache (not touched by 'image prune') is what fills the disk over time.
# Drop cache older than 7 days; keep recent layers so the next build stays fast.
sudo docker builder prune -f --filter "until=168h"

mkdir -p logs
date -u +"%Y-%m-%dT%H:%M:%SZ commit=$(git rev-parse --short HEAD)" > logs/last_deploy.txt

echo "==> Deploy complete"
cat logs/last_deploy.txt
sudo docker ps --filter name=hitchhiking-map
