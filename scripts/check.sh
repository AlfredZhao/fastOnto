#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
conda run --no-capture-output -n fastonto python -m pytest -q
conda run --no-capture-output -n fastonto python -m pip check
cd frontend
npm run build
npm run test:config
npm test -- --workers=2
