#!/usr/bin/env bash
set -euo pipefail
exec bash "$(dirname "$0")/_lifecycle.sh" restart-backend "$@"
