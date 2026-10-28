#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
if ! command -v conda >/dev/null 2>&1; then
  printf '%s\n' '找不到 conda；请先加载 Conda，并确认存在 fastonto 环境。' >&2
  exit 1
fi
exec conda run --no-capture-output -n fastonto python "$SCRIPT_DIR/service_manager.py" "$@"
