#!/usr/bin/env bash
# Start the Part 107 course. Requires Python 3.8 or newer; nothing to install.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON=$(command -v python3 || command -v python || true)
if [ -z "$PYTHON" ]; then
  echo "Python 3 is required but was not found. Install Python 3, then run this again."
  exit 1
fi

PORT=$("$PYTHON" -c 'import json;print(json.load(open("config.json")).get("port",8107))')
"$PYTHON" server.py "$@" &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null || true' EXIT

sleep 1
URL="http://localhost:${PORT}"
if command -v open >/dev/null 2>&1; then open "$URL"
elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL"
else echo "Open $URL in your browser."
fi

wait $SERVER_PID
