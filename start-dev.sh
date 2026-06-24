#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
FRONTEND_DIR="$PROJECT_DIR/frontend"
BACKEND_DIR="$PROJECT_DIR/backend"
LOG_DIR="$PROJECT_DIR/logs"
RUN_DIR="$PROJECT_DIR/run"
FRONTEND_PORT="${FRONTEND_PORT:-50001}"
BACKEND_PORT="${BACKEND_PORT:-8000}"

FRONTEND_LOG="$LOG_DIR/frontend.log"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_PID_FILE="$RUN_DIR/frontend.pid"
BACKEND_PID_FILE="$RUN_DIR/backend.pid"
WINDOWS_PROXY_SCRIPT="$PROJECT_DIR/scripts/windows_tcp_proxy.py"
FRONTEND_PROXY_PID_FILE="$RUN_DIR/frontend-winproxy.pid"
BACKEND_PROXY_PID_FILE="$RUN_DIR/backend-winproxy.pid"

info() {
  printf '[INFO] %s\n' "$1"
}

warn() {
  printf '[WARN] %s\n' "$1"
}

error() {
  printf '[ERROR] %s\n' "$1" >&2
}

require_dir() {
  local dir_path="$1"
  local label="$2"

  if [[ ! -d "$dir_path" ]]; then
    error "缺少 ${label} 目录: $dir_path"
    exit 1
  fi
}

require_command() {
  local command_name="$1"
  local label="$2"

  if ! command -v "$command_name" >/dev/null 2>&1; then
    error "未检测到 ${label}: $command_name"
    exit 1
  fi
}

cleanup_stale_pid() {
  local pid_file="$1"
  local label="$2"

  if [[ ! -f "$pid_file" ]]; then
    return
  fi

  local pid
  pid="$(cat "$pid_file")"

  if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
    error "${label} 已在运行中，PID=$pid"
    exit 1
  fi

  warn "${label} 的 PID 文件已过期，自动清理: $pid_file"
  rm -f "$pid_file"
}

cleanup_stale_windows_pid() {
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

  if powershell.exe -NoProfile -Command "if (Get-Process -Id $pid -ErrorAction SilentlyContinue) { exit 0 } exit 1" >/dev/null 2>&1; then
    error "${label} 已在运行中，PID=$pid"
    exit 1
  fi

  warn "${label} 的 PID 文件已过期，自动清理: $pid_file"
  rm -f "$pid_file"
}

detect_access_ip() {
  if command -v hostname >/dev/null 2>&1; then
    local host_ip
    host_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
    if [[ -n "${host_ip:-}" ]]; then
      printf '%s' "$host_ip"
      return
    fi
  fi

  printf '127.0.0.1'
}

has_windows_python() {
  powershell.exe -NoProfile -Command "if (Get-Command python -ErrorAction SilentlyContinue) { exit 0 } exit 1" >/dev/null 2>&1
}

is_windows_port_in_use() {
  local port="$1"
  powershell.exe -NoProfile -Command "if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) { exit 0 } exit 1" >/dev/null 2>&1
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

  if command -v netstat >/dev/null 2>&1; then
    netstat -tln 2>/dev/null | awk -v pattern=":${port}" '$4 ~ pattern"$" { found=1 } END { exit found ? 0 : 1 }'
    return
  fi

  return 1
}

print_port_owner() {
  local port="$1"

  if command -v ss >/dev/null 2>&1; then
    ss -ltnp 2>/dev/null | awk -v pattern=":${port}" '$4 ~ pattern"$" { print "  " $0 }'
    return
  fi

  if command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | sed 's/^/  /'
    return
  fi

  if command -v netstat >/dev/null 2>&1; then
    netstat -tlnp 2>/dev/null | awk -v pattern=":${port}" '$4 ~ pattern"$" { print "  " $0 }'
  fi
}

find_port_pids() {
  local port="$1"
  local pids=""

  if command -v ss >/dev/null 2>&1; then
    pids="$(ss -ltnp 2>/dev/null | awk -v pattern=":${port}" '
      $4 ~ pattern"$" {
        while (match($0, /pid=[0-9]+/)) {
          print substr($0, RSTART + 4, RLENGTH - 4)
          $0 = substr($0, RSTART + RLENGTH)
        }
      }
    ' | sort -u)"
    if [[ -n "${pids:-}" ]]; then
      printf '%s\n' "$pids"
      return
    fi
  fi

  if command -v lsof >/dev/null 2>&1; then
    lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u
    return
  fi

  if command -v netstat >/dev/null 2>&1; then
    netstat -tlnp 2>/dev/null | awk -v pattern=":${port}" '
      $4 ~ pattern"$" && $6 == "LISTEN" {
        split($7, parts, "/")
        if (parts[1] ~ /^[0-9]+$/) print parts[1]
      }
    ' | sort -u
  fi
}

require_port_free() {
  local port="$1"
  local label="$2"

  if is_port_in_use "$port"; then
    error "${label} 端口 ${port} 已被占用"
    print_port_owner "$port"
    printf '  建议先执行: bash stop-dev.sh\n' >&2
    exit 1
  fi
}

detect_python() {
  if command -v python3 >/dev/null 2>&1; then
    printf 'python3'
    return
  fi

  if command -v python >/dev/null 2>&1; then
    printf 'python'
    return
  fi

  error "未检测到 Python，请先安装 python3 或 python"
  exit 1
}

detect_backend_script() {
  if [[ -f "$BACKEND_DIR/src/main.py" ]]; then
    printf 'src/main.py'
    return
  fi

  if [[ -f "$BACKEND_DIR/src/app.py" ]]; then
    printf 'src/app.py'
    return
  fi

  error "未找到后端入口文件，请创建 backend/src/main.py 或 backend/src/app.py"
  exit 1
}

verify_frontend_entry() {
  if [[ ! -f "$FRONTEND_DIR/package.json" ]]; then
    error "frontend/package.json 不存在，前端尚未初始化"
    exit 1
  fi

  if [[ ! -f "$FRONTEND_DIR/src/dev-server.js" ]]; then
    error "未找到 frontend/src/dev-server.js，前端入口缺失"
    exit 1
  fi
}

start_frontend() {
  info "启动前端..."

  (
    cd "$FRONTEND_DIR"
    : > "$FRONTEND_LOG"
    PORT="$FRONTEND_PORT" setsid -f node src/dev-server.js > "$FRONTEND_LOG" 2>&1
  )

  sleep 1

  if ! is_port_in_use "$FRONTEND_PORT"; then
    error "前端未成功监听端口 ${FRONTEND_PORT}，请查看日志: $FRONTEND_LOG"
    rm -f "$FRONTEND_PID_FILE"
    exit 1
  fi

  local pid
  pid="$(find_port_pids "$FRONTEND_PORT" | head -n 1)"
  if [[ -z "${pid:-}" ]]; then
    error "前端已监听端口 ${FRONTEND_PORT}，但未能解析到 PID"
    rm -f "$FRONTEND_PID_FILE"
    exit 1
  fi

  printf '%s\n' "$pid" > "$FRONTEND_PID_FILE"

  info "前端已启动，PID=$pid，日志: $FRONTEND_LOG"

  local access_ip
  access_ip="$(detect_access_ip)"
  printf '  frontend host: 0.0.0.0\n'
  printf '  frontend port: %s\n' "$FRONTEND_PORT"
  printf '  frontend url : http://localhost:%s\n' "$FRONTEND_PORT"
  printf '  frontend lan : http://%s:%s\n' "$access_ip" "$FRONTEND_PORT"
}

start_backend() {
  local python_cmd="$1"
  local backend_script="$2"

  info "启动后端..."

  (
    cd "$BACKEND_DIR"
    PORT="$BACKEND_PORT" nohup "$python_cmd" "$backend_script" > "$BACKEND_LOG" 2>&1 &
    echo $! > "$BACKEND_PID_FILE"
  )

  sleep 1

  local pid
  pid="$(cat "$BACKEND_PID_FILE")"

  if ! kill -0 "$pid" >/dev/null 2>&1; then
    error "后端启动失败，请查看日志: $BACKEND_LOG"
    rm -f "$BACKEND_PID_FILE"
    exit 1
  fi

  if ! is_port_in_use "$BACKEND_PORT"; then
    error "后端未成功监听端口 ${BACKEND_PORT}，请查看日志: $BACKEND_LOG"
    rm -f "$BACKEND_PID_FILE"
    exit 1
  fi

  info "后端已启动，PID=$pid，日志: $BACKEND_LOG"

  local access_ip
  access_ip="$(detect_access_ip)"
  printf '  backend  host: 0.0.0.0\n'
  printf '  backend  port: %s\n' "$BACKEND_PORT"
  printf '  backend  url : http://localhost:%s\n' "$BACKEND_PORT"
  printf '  backend  lan : http://%s:%s\n' "$access_ip" "$BACKEND_PORT"
}

start_windows_proxy() {
  local listen_port="$1"
  local remote_host="$2"
  local remote_port="$3"
  local pid_file="$4"
  local label="$5"

  if ! has_windows_python; then
    warn "Windows 未检测到 python，无法建立 ${label}"
    return
  fi

  if is_windows_port_in_use "$listen_port"; then
    warn "Windows 本地端口 ${listen_port} 已被占用，跳过 ${label}"
    return
  fi

  local script_win
  script_win="$(wslpath -w "$WINDOWS_PROXY_SCRIPT")"

  local pid
  pid="$(
    powershell.exe -NoProfile -Command "\$proc = Start-Process -FilePath python -ArgumentList @('$script_win','--listen-host','127.0.0.1','--listen-port','$listen_port','--remote-host','$remote_host','--remote-port','$remote_port','--label','$label') -WindowStyle Hidden -PassThru; \$proc.Id" \
      | tr -d '\r'
  )"

  sleep 1

  if ! is_windows_port_in_use "$listen_port"; then
    warn "${label} 启动失败，Windows localhost:${listen_port} 仍不可用"
    return
  fi

  printf '%s\n' "$pid" > "$pid_file"
  info "${label} 已启动，PID=$pid"
}

main() {
  mkdir -p "$LOG_DIR" "$RUN_DIR"

  require_dir "$FRONTEND_DIR" "frontend"
  require_dir "$BACKEND_DIR" "backend"

  require_command "node" "Node.js"
  require_command "npm" "npm"

  local python_cmd
  python_cmd="$(detect_python)"

  verify_frontend_entry

  local backend_script
  backend_script="$(detect_backend_script)"

  cleanup_stale_pid "$FRONTEND_PID_FILE" "前端"
  cleanup_stale_pid "$BACKEND_PID_FILE" "后端"
  cleanup_stale_windows_pid "$FRONTEND_PROXY_PID_FILE" "前端本地代理"
  cleanup_stale_windows_pid "$BACKEND_PROXY_PID_FILE" "后端本地代理"
  require_port_free "$FRONTEND_PORT" "前端"
  require_port_free "$BACKEND_PORT" "后端"

  start_frontend
  start_backend "$python_cmd" "$backend_script"
  local access_ip
  access_ip="$(detect_access_ip)"
  start_windows_proxy "$FRONTEND_PORT" "$access_ip" "$FRONTEND_PORT" "$FRONTEND_PROXY_PID_FILE" "前端本地代理"
  start_windows_proxy "$BACKEND_PORT" "$access_ip" "$BACKEND_PORT" "$BACKEND_PROXY_PID_FILE" "后端本地代理"

  info "启动完成"
  printf '  frontend log: %s\n' "$FRONTEND_LOG"
  printf '  backend  log: %s\n' "$BACKEND_LOG"
  printf '  frontend pid: %s\n' "$FRONTEND_PID_FILE"
  printf '  backend  pid: %s\n' "$BACKEND_PID_FILE"
  if [[ -f "$FRONTEND_PROXY_PID_FILE" ]]; then
    printf '  win front pid: %s\n' "$FRONTEND_PROXY_PID_FILE"
  fi
  if [[ -f "$BACKEND_PROXY_PID_FILE" ]]; then
    printf '  win back  pid: %s\n' "$BACKEND_PROXY_PID_FILE"
  fi
}

main "$@"
