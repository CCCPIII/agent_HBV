#!/usr/bin/env bash
# Start backend + open frontend HTML in browser.
# Usage: ./start.sh
set -e

cd "$(dirname "$0")"

echo "=== Investment Agent System ==="

# Check .env exists
if [ ! -f .env ]; then
  echo "ERROR: .env not found. Run ./setup.sh first."
  exit 1
fi

# Kill any existing backend on port 8000
if lsof -ti:8000 &>/dev/null; then
  echo "Stopping existing backend on port 8000..."
  lsof -ti:8000 | xargs kill -9 2>/dev/null || true
  sleep 1
fi

# Start backend in background
echo "Starting backend API on http://localhost:8000 ..."
PYTHONPATH=. uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level warning &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

# Wait for backend to be ready
echo -n "Waiting for backend"
for i in $(seq 1 20); do
  if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo " ready!"
    break
  fi
  echo -n "."
  sleep 1
done

# Open frontend HTML in default browser
FRONTEND="$(pwd)/frontend/index.html"
echo ""
echo "Opening frontend: $FRONTEND"

if command -v xdg-open &>/dev/null; then
  xdg-open "$FRONTEND" &
elif command -v open &>/dev/null; then
  open "$FRONTEND" &
else
  echo "Open this file in your browser: $FRONTEND"
fi

echo ""
echo "=== System running ==="
echo "  Backend API:  http://localhost:8000"
echo "  API Docs:     http://localhost:8000/docs"
echo "  Frontend:     $FRONTEND"
echo ""
echo "Press Ctrl+C to stop."

# Keep script alive until Ctrl+C
wait $BACKEND_PID
