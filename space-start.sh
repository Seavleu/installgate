#!/bin/sh
# Hugging Face Spaces: one container, Next on $PORT, API on loopback :8000.
set -eu
export PATH="/app/.venv/bin:${PATH}"
export CACHE_PATH="${CACHE_PATH:-/app/.cache/installgate.sqlite}"
export API_URL="${API_URL:-http://127.0.0.1:8000}"
export HOSTNAME=0.0.0.0
export PORT="${PORT:-7860}"
export RATE_LIMIT_TRUST_PROXY="${RATE_LIMIT_TRUST_PROXY:-true}"
mkdir -p /app/.cache

uvicorn mcp_server.api:app --host 127.0.0.1 --port 8000 &
i=0
while [ "$i" -lt 40 ]; do
  python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)" \
    >/dev/null 2>&1 && break
  i=$((i + 1))
  sleep 0.5
done

cd /app/ui
exec node server.js
