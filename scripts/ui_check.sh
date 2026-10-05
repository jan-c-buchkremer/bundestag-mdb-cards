#!/bin/sh
# scripts/ui_check.py in the Playwright container, for a machine without Chromium's system libraries (server-jan).
#   scripts/ui_check.sh [site, default data/out] [options of ui_check.py]
# Paths must lie inside this repository (it is mounted as /w). The image's Playwright version is pinned to the one
# in uv.lock, so the browser matches.
set -eu
cd "$(dirname "$0")/.."
site=${1:-data/out}
[ $# -gt 0 ] && shift
exec docker run --rm --network host -u "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD:/w" -w /w \
    mcr.microsoft.com/playwright/python:v1.55.0-noble \
    sh -c 'pip install -q --user playwright==1.55.0 pillow >/dev/null 2>&1; exec python scripts/ui_check.py "$@"' \
    ui_check "$site" "$@"
