#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$SCRIPT_DIR/run"
FRONTEND_PID_FILE="$RUN_DIR/frontend.pid"
BACKEND_PID_FILE="$RUN_DIR/backend.pid"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PROXY_PID_FILE="$RUN_DIR/frontend-winproxy.pid"
BACKEND_PROXY_PID_FILE="$RUN_DIR/backend-winproxy.pid"

print_service_status() {
  local label="$1"
  local pid_file="$2"
  local port="$3"

  printf '%s\n' "[INFO] ${label}"
  printf '  port: %s\n' "$port"

  if [[ -f "$pid_file" ]]; then
    local pid
    pid="$(cat "$pid_file")"
    printf '  pid : %s\n' "$pid"
    if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
      printf '  run : running\n'
    else
      printf '  run : stale pid\n'
    fi
  else
    printf '  pid : not found\n'
    printf '  run : stopped\n'
  fi

  if command -v ss >/dev/null 2>&1; then
    printf '  net : '
    if ss -ltn 2>/dev/null | awk -v pattern=":${port}" '$4 ~ pattern"$" { found=1 } END { exit found ? 0 : 1 }'; then
      printf 'listening\n'
    else
      printf 'not listening\n'
    fi
  fi
}

main() {
  print_service_status "前端" "$FRONTEND_PID_FILE" "$FRONTEND_PORT"
  print_service_status "后端" "$BACKEND_PID_FILE" "$BACKEND_PORT"
  if command -v powershell.exe >/dev/null 2>&1; then
    printf '%s\n' "[INFO] Windows 本地代理"
    if [[ -f "$FRONTEND_PROXY_PID_FILE" ]]; then
      printf '  frontend proxy pid: %s\n' "$(cat "$FRONTEND_PROXY_PID_FILE")"
    fi
    if [[ -f "$BACKEND_PROXY_PID_FILE" ]]; then
      printf '  backend  proxy pid: %s\n' "$(cat "$BACKEND_PROXY_PID_FILE")"
    fi
    printf '  localhost 5173: '
    if powershell.exe -NoProfile -Command "if (Get-NetTCPConnection -LocalPort $FRONTEND_PORT -State Listen -ErrorAction SilentlyContinue) { exit 0 } exit 1" >/dev/null 2>&1; then
      printf 'listening\n'
    else
      printf 'not listening\n'
    fi
    printf '  localhost 8000: '
    if powershell.exe -NoProfile -Command "if (Get-NetTCPConnection -LocalPort $BACKEND_PORT -State Listen -ErrorAction SilentlyContinue) { exit 0 } exit 1" >/dev/null 2>&1; then
      printf 'listening\n'
    else
      printf 'not listening\n'
    fi
  fi
}

main "$@"
