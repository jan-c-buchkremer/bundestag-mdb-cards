#!/bin/sh
# Share the local preview (`uv run cards preview`, http://127.0.0.1:8000) on the tailnet until Ctrl-C, to check it on
# a phone or show it to a tester: https://<this machine>.<tailnet>.ts.net:8445/. Tailnet only, nothing public, and
# nothing stays configured after Ctrl-C (never use `tailscale serve reset`: it drops the machine's other Serve ports).
#   scripts/stage.sh [port]    the preview's local port, default 8000
# 443, 8443 and 8444 are taken on server-jan (8444: the public site's preview), hence 8445.
# Needs once: sudo tailscale set --operator=$USER
exec tailscale serve --https=8445 "http://127.0.0.1:${1:-8000}"
