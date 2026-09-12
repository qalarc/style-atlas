#!/bin/bash
# restart.sh — safely restart the Style Atlas server (never self-matching).
# Kills by PORT owner, not by command-line pattern.
PORT="${1:-1340}"
DIR="$(cd "$(dirname "$0")" && pwd)"

# kill whoever holds the port
PID=$(ss -tlnp 2>/dev/null | grep ":$PORT " | grep -oP 'pid=\K[0-9]+' | head -1)
if [ -n "$PID" ]; then
  kill -9 "$PID" 2>/dev/null
  sleep 1
fi

cd "$DIR"
setsid python3 atlas_server.py --port "$PORT" > /tmp/atlas.log 2>&1 < /dev/null &
sleep 1.5
curl -s --max-time 5 -o /dev/null -w "atlas :$PORT → %{http_code}\n" "http://localhost:$PORT/" || true
