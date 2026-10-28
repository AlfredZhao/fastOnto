#!/usr/bin/env bash
set -euo pipefail
# Compatibility only: both names share the same lock, PID state and stop script.
printf '%s\n' '兼容入口：请改用 start-frontend.sh --local；这不是另一套前端服务。' >&2
exec bash "$(dirname "$0")/start-frontend.sh" --local "$@"
