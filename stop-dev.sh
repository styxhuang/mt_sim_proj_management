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

info() {
  printf '[INFO] %s\n' "$1"
}

warn() {
  printf '[WARN] %s\n' "$1"
}

stop_windows_service() {
  local pid_file="$1"
  local label="$2"

  if [[ ! -f "$pid_file" ]]; then
    return
  fi

  local pid
  pid="$(cat "$pid_file")"

  if [[ -z "$pid" ]]; then
    rm -f "$pid_file"
    return
  fi

  if powershell.exe -NoProfile -Command "if (Get-Process -Id $pid -ErrorAction SilentlyContinue) { Stop-Process -Id $pid -Force; exit 0 } exit 1" >/dev/null 2>&1; then
    info "停止 ${label}，PID=$pid"
  else
    warn "${label} 进程不存在，自动清理过期 PID: $pid"
  fi

  rm -f "$pid_file"
}

is_port_in_use() {
  local port="$1"

  if command -v ss >/dev/null 2>&1; then
    ss -ltn 2>/dev/null | awk -v pattern=":${port}" '$4 ~ pattern"$" { found=1 } END { exit found ? 0 : 1 }'
    return
  fi

  if command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
    return
  fi

  return 1
}

find_port_pids() {
  local port="$1"

  if command -v ss >/dev/null 2>&1; then
    ss -ltnp 2>/dev/null | awk -v pattern=":${port}" '
      $4 ~ pattern"$" {
        while (match($0, /pid=[0-9]+/)) {
          print substr($0, RSTART + 4, RLENGTH - 4)
          $0 = substr($0, RSTART + RLENGTH)
        }
      }
    ' | sort -u
    return
  fi

  if command -v lsof >/dev/null 2>&1; then
    lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u
  fi
}

stop_service() {
  local pid_file="$1"
  local label="$2"

  if [[ ! -f "$pid_file" ]]; then
    warn "${label} 未在运行，PID 文件不存在: $pid_file"
    return
  fi

  local pid
  pid="$(cat "$pid_file")"

  if [[ -z "$pid" ]]; then
    warn "${label} 的 PID 文件为空，自动清理: $pid_file"
    rm -f "$pid_file"
    return
  fi

  if ! kill -0 "$pid" >/dev/null 2>&1; then
    warn "${label} 进程不存在，自动清理过期 PID: $pid"
    rm -f "$pid_file"
    return
  fi

  info "停止 ${label}，PID=$pid"
  kill "$pid"

  local attempts=0
  while kill -0 "$pid" >/dev/null 2>&1; do
    attempts=$((attempts + 1))
    if [[ "$attempts" -ge 10 ]]; then
      warn "${label} 未在预期时间内退出，执行强制停止"
      kill -9 "$pid" >/dev/null 2>&1 || true
      break
    fi
    sleep 1
  done

  rm -f "$pid_file"
  info "${label} 已停止"
}

stop_port_owner() {
  local port="$1"
  local label="$2"

  if ! is_port_in_use "$port"; then
    return
  fi

  local pids
  pids="$(find_port_pids "$port")"

  if [[ -z "${pids:-}" ]]; then
    warn "${label} 端口 ${port} 仍被占用，但未解析到具体 PID"
    return
  fi

  while IFS= read -r pid; do
    [[ -z "$pid" ]] && continue
    if ! kill -0 "$pid" >/dev/null 2>&1; then
      continue
    fi

    info "按端口停止 ${label} 残留进程，PID=$pid，PORT=$port"
    kill "$pid" >/dev/null 2>&1 || true

    local attempts=0
    while kill -0 "$pid" >/dev/null 2>&1; do
      attempts=$((attempts + 1))
      if [[ "$attempts" -ge 5 ]]; then
        warn "${label} 端口残留进程未退出，执行强制停止，PID=$pid"
        kill -9 "$pid" >/dev/null 2>&1 || true
        break
      fi
      sleep 1
    done
  done <<< "$pids"
}

stop_windows_port_owner() {
  local port="$1"
  local label="$2"

  powershell.exe -NoProfile -Command "\$owners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique; foreach (\$pid in \$owners) { try { Stop-Process -Id \$pid -Force -ErrorAction Stop } catch {} }" >/dev/null 2>&1 || true
  info "${label} Windows localhost:${port} 已清理"
}

main() {
  stop_service "$FRONTEND_PID_FILE" "前端"
  stop_service "$BACKEND_PID_FILE" "后端"
  stop_windows_service "$FRONTEND_PROXY_PID_FILE" "前端本地代理"
  stop_windows_service "$BACKEND_PROXY_PID_FILE" "后端本地代理"
  stop_port_owner "$FRONTEND_PORT" "前端"
  stop_port_owner "$BACKEND_PORT" "后端"
  stop_windows_port_owner "$FRONTEND_PORT" "前端本地代理"
  stop_windows_port_owner "$BACKEND_PORT" "后端本地代理"
  info "停止流程结束"
}

main "$@"
