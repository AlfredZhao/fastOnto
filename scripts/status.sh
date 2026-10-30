#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
local=false
if (($# == 1)) && [[ "$1" == "--local" ]]; then
  local=true
elif (($# != 0)); then
  echo '用法：status.sh [--local]；默认检查 backend 与 HTTPS gateway，--local 检查 backend 与本机 Vite。' >&2
  exit 2
fi
failed=0
bash "$SCRIPT_DIR/status-backend.sh" || failed=1
if "$local"; then
  bash "$SCRIPT_DIR/status-frontend.sh" || failed=1
else
  bash "$SCRIPT_DIR/status-gateway.sh" || failed=1
fi
exit "$failed"
