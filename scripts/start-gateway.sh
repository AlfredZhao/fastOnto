#!/usr/bin/env bash
set -euo pipefail
# HTTPS static frontend + API reverse proxy. Does not stop Vite or alter Nginx/firewall.
exec bash "$(dirname "$0")/_service.sh" gateway start "$@"
