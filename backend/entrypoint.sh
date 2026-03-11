#!/bin/sh
set -e

# Railway injects PORT, default to 8000 for local dev
PORT=${PORT:-8000}

echo "Starting uvicorn on port $PORT"

exec python -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "$PORT"
