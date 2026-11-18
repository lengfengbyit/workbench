#!/usr/bin/env bash
# Restart the workbench in the background: stop the old process, start a new one, wait until the port answers.
# Usage: ./restart.sh [port]        ./restart.sh stop        env: HOST (default 127.0.0.1), WORKBENCH_HOME
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
HOME_DIR="${WORKBENCH_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/workbench}"
PORT="${1:-8765}"
HOST="${HOST:-127.0.0.1}"
PID_FILE="$HOME_DIR/app.pid"
LOG_DIR="$HOME_DIR/logs"
LOG="$LOG_DIR/app.log"

stop() {
  local pids=""
  [[ -f "$PID_FILE" ]] && pids="$(cat "$PID_FILE")"
  for pid in $pids; do
    kill -0 "$pid" 2>/dev/null || continue
    kill "$pid"
    for _ in $(seq 1 50); do kill -0 "$pid" 2>/dev/null || break; sleep 0.1; done
    kill -0 "$pid" 2>/dev/null && kill -9 "$pid"
    echo "stopped old process $pid"
  done
  rm -f "$PID_FILE"
}

if [[ "$PORT" == "stop" ]]; then
  stop
  exit 0
fi

stop
mkdir -p "$LOG_DIR"
# rotate the log once it passes 5 MB
[[ -f "$LOG" && $(wc -c <"$LOG") -gt 5242880 ]] && mv -f "$LOG" "$LOG.1"

cd "$DIR"
# setsid detaches from the terminal's session; macOS does not ship it, nohup alone is enough there
DETACH=nohup
command -v setsid >/dev/null 2>&1 && DETACH="setsid nohup"
$DETACH python3 -m workbench serve --host "$HOST" --port "$PORT" >>"$LOG" 2>&1 < /dev/null &
echo $! > "$PID_FILE"

for _ in $(seq 1 30); do
  if curl -s -m 2 -o /dev/null "http://127.0.0.1:$PORT/"; then
    echo "started: pid $(cat "$PID_FILE"), http://$HOST:$PORT/  log $LOG"
    exit 0
  fi
  kill -0 "$(cat "$PID_FILE")" 2>/dev/null || break
  sleep 0.3
done
echo "failed to start, last log lines:" >&2
tail -n 20 "$LOG" >&2
exit 1
