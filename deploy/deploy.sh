#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Fetching latest main"
git fetch --prune origin main
git reset --hard origin/main

echo "==> Rebuilding and restarting container"
sudo docker compose up -d --build

echo "==> Pruning dangling images"
sudo docker image prune -f

mkdir -p logs
date -u +"%Y-%m-%dT%H:%M:%SZ commit=$(git rev-parse --short HEAD)" > logs/last_deploy.txt

echo "==> Deploy complete"
cat logs/last_deploy.txt
sudo docker ps --filter name=hitchhiking-map
