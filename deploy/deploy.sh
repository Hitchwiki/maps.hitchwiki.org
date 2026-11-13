#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Fetching latest main"
git fetch --prune origin main
git reset --hard origin/main

# Disk guard: a full disk fails the build mid-way (Errno 28, 2026-11-13) and leaves merged
# work undeployed. Log free space, and if under 3 GB reclaim unused docker layers first.
free_kb=$(df -Pk . | awk 'NR==2{print $4}')
echo "==> Disk free: $(( free_kb / 1024 )) MB"
if [ "$free_kb" -lt 3145728 ]; then
  echo "==> Low disk, pruning unused docker images and build cache first"
  sudo docker image prune -af --filter "until=24h" || true
  sudo docker builder prune -af --filter "until=24h" || true
  free_kb=$(df -Pk . | awk 'NR==2{print $4}')
  echo "==> Disk free after prune: $(( free_kb / 1024 )) MB"
  if [ "$free_kb" -lt 1048576 ]; then
    echo "!! Under 1 GB free after pruning; aborting before the build. Free disk space on the server." >&2
    # Read-only diagnostics: name what is using the disk (the abort is the last thing this run does).
    echo "==> Disk diagnostics (read-only)" >&2
    du -xsh db logs dist hitch/static 2>/dev/null >&2 || true
    sudo docker system df >&2 || true
    sudo du -xsh /var/lib/docker/containers /var/lib/docker/overlay2 /var/lib/docker/volumes 2>/dev/null >&2 || true
    sudo du -xh --max-depth=1 / 2>/dev/null | sort -h | tail -8 >&2 || true
    sudo du -xh --max-depth=2 /var /opt 2>/dev/null | sort -h | tail -14 >&2 || true
    sudo docker system df -v 2>/dev/null | sed -n '/Local Volumes/,/Build cache/p' | sort -k3 -h | tail -8 >&2 || true
    exit 1
  fi
fi

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
