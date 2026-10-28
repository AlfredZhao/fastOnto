#!/usr/bin/env bash
set -euo pipefail
# Default: explicitly approved temporary public HTTP. --local uses loopback.
exec bash "$(dirname "$0")/_service.sh" frontend start "$@"
