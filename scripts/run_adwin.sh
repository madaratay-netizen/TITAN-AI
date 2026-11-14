#!/usr/bin/env bash
# ADWIN OS — start the backend + dashboard (Linux/macOS).
# Run from the repo root:  bash scripts/run_adwin.sh
set -euo pipefail

cd "$(dirname "$0")/.."

# Ensure the local AI runtime is up (offline inference).
if command -v ollama >/dev/null 2>&1; then
  if ! curl -fsS http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
    (ollama serve >/tmp/ollama.log 2>&1 &)
    sleep 3
  fi
fi

PY="./.venv/bin/python"
[ -x "$PY" ] || PY="python3"

echo "Starting ADWIN OS at http://127.0.0.1:8077  (Ctrl+C to stop)"
# Open the dashboard in the default browser shortly after the server starts.
( sleep 3; command -v xdg-open >/dev/null 2>&1 && xdg-open http://127.0.0.1:8077 >/dev/null 2>&1 || true ) &

exec "$PY" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8077
