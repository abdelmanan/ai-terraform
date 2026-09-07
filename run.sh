#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

source .venv/bin/activate

uvicorn backend.app:app --reload --port 8000 &
BACKEND_PID=$!

(cd frontend && python3 -m http.server 5173) &
FRONTEND_PID=$!

trap 'kill $BACKEND_PID $FRONTEND_PID 2>/dev/null' EXIT INT TERM

echo "Backend  : http://localhost:8000"
echo "Frontend : http://localhost:5173"
echo "Ctrl+C pour tout arrêter."

wait
