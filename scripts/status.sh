#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
failed=0
bash "$SCRIPT_DIR/status-backend.sh" "$@" || failed=1
bash "$SCRIPT_DIR/status-frontend.sh" "$@" || failed=1
exit "$failed"
