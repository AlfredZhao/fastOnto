#!/usr/bin/env bash
# Shared orchestration. Default whole-stack mode is HTTPS gateway; --local uses Vite on loopback.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
operation="${1:?需要生命周期操作}"
shift
start_args=()
stop_args=()
local_args=()
while (($#)); do
  case "$1" in
    --help|-h)
      printf '%s\n' "用法：$operation [--timeout 1..300] [--local] [--force]" \
        '--local：整体服务使用本机 Vite 前端；默认使用 HTTPS gateway。--force：仅停止/重启，优雅停止超时后强制结束。' \
        '整体启动后端→gateway；整体停止 gateway→后端；重启在 stop 成功后才 start。'
      exit 0 ;;
    --local)
      case "$operation" in start-all|stop-all|restart-all|restart-frontend) local_args=(--local);; *) echo '此操作不支持 --local' >&2; exit 2;; esac
      shift ;;
    --force)
      case "$operation" in stop-all|restart-*) stop_args+=(--force);; *) echo '此操作不支持 --force' >&2; exit 2;; esac
      shift ;;
    --timeout)
      if (($# < 2)) || [[ ! "$2" =~ ^[0-9]{1,3}$ ]] || ((10#$2 < 1 || 10#$2 > 300)); then
        echo '--timeout 必须是 1–300 秒的整数' >&2; exit 2
      fi
      start_args+=(--timeout "$2"); stop_args+=(--timeout "$2"); shift 2 ;;
    *) printf '未知参数：%s\n' "$1" >&2; exit 2 ;;
  esac
done
case "$operation" in
  start-all)
    bash "$SCRIPT_DIR/start-backend.sh" "${start_args[@]}"
    if [[ ${#local_args[@]} -gt 0 ]]; then target="frontend"; else target="gateway"; fi
    if ! bash "$SCRIPT_DIR/start-$target.sh" "${start_args[@]}" "${local_args[@]}"; then
      echo "$target 启动失败；后端状态保留（可能此前已运行）。请运行 status.sh 检查。" >&2
      exit 1
    fi ;;
  stop-all)
    failed=0
    if [[ ${#local_args[@]} -gt 0 ]]; then target="frontend"; else target="gateway"; fi
    bash "$SCRIPT_DIR/stop-$target.sh" "${stop_args[@]}" || failed=1
    bash "$SCRIPT_DIR/stop-backend.sh" "${stop_args[@]}" || failed=1
    exit "$failed" ;;
  restart-backend)
    bash "$SCRIPT_DIR/stop-backend.sh" "${stop_args[@]}"
    bash "$SCRIPT_DIR/start-backend.sh" "${start_args[@]}" ;;
  restart-frontend)
    bash "$SCRIPT_DIR/stop-frontend.sh" "${stop_args[@]}"
    bash "$SCRIPT_DIR/start-frontend.sh" "${start_args[@]}" "${local_args[@]}" ;;
  restart-gateway)
    bash "$SCRIPT_DIR/stop-gateway.sh" "${stop_args[@]}"
    bash "$SCRIPT_DIR/start-gateway.sh" "${start_args[@]}" ;;
  restart-all)
    bash "$SCRIPT_DIR/stop-all.sh" "${stop_args[@]}" "${local_args[@]}"
    bash "$SCRIPT_DIR/start-all.sh" "${start_args[@]}" "${local_args[@]}" ;;
  *) echo '未知生命周期操作' >&2; exit 2 ;;
esac
