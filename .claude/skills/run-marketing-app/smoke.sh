#!/usr/bin/env bash
# Driver for the marketing-app FastAPI backend: launches the server,
# drives the two real endpoints with the committed fixture PDFs, and
# shuts down cleanly. One command; exit code tells you if it's healthy.
#
# Usage: .claude/skills/run-marketing-app/smoke.sh   (run from repo root)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

PORT="${PORT:-8000}"
LOG="/tmp/marketing-app-smoke.log"

if [ ! -d .venv ]; then
  echo "== No .venv found — creating one with python3.12 and installing deps (first run only) =="
  PYBIN="$(command -v python3.12 || command -v python3.11 || true)"
  if [ -z "$PYBIN" ]; then
    echo "FAIL: need python3.11+ (python3.12 preferred). Install via 'brew install python@3.12' or apt." >&2
    exit 1
  fi
  "$PYBIN" -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -q --upgrade pip
  pip install -q -e ".[dev]"
else
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "== Freeing port $PORT if in use =="
lsof -ti:"$PORT" -sTCP:LISTEN | xargs -r kill 2>/dev/null || true
sleep 1

echo "== Resetting local storage (stopped server only — never wipe storage/ while it's running, it corrupts the open SQLite handle) =="
rm -rf storage
mkdir -p storage

echo "== Starting uvicorn on :$PORT (log: $LOG) =="
uvicorn app.main:app --port "$PORT" &> "$LOG" &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT

echo "== Waiting for readiness =="
ready=false
for _ in $(seq 1 30); do
  if curl -sf "http://localhost:$PORT/health" > /dev/null; then
    ready=true
    break
  fi
  sleep 1
done
if [ "$ready" != true ]; then
  echo "FAIL: server did not become healthy within 30s. Last 40 log lines:" >&2
  tail -40 "$LOG" >&2
  exit 1
fi
echo "OK: $(curl -s "http://localhost:$PORT/health")"

echo "== Uploading sender fixture (Nexus Vision AI) =="
SENDER_RESP=$(curl -sf -X POST "http://localhost:$PORT/companies/NexusVisionAI/documents?role=sender" \
  -F "files=@tests/fixtures/sender_company_context.pdf")
echo "$SENDER_RESP"
echo "$SENDER_RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['documents'][0]['chunk_count'] > 0; assert d['documents'][0]['image_count'] > 0" \
  && echo "OK: sender PDF parsed (chunks + image extracted)" \
  || { echo "FAIL: sender upload response missing expected fields" >&2; exit 1; }

echo "== Uploading receiver fixture (Apex Global Logistics) =="
RECEIVER_RESP=$(curl -sf -X POST "http://localhost:$PORT/companies/ApexGlobalLogistics/documents?role=receiver" \
  -F "files=@tests/fixtures/receiver_company_context.pdf")
echo "$RECEIVER_RESP"
echo "$RECEIVER_RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['documents'][0]['chunk_count'] > 0; assert d['documents'][0]['image_count'] > 0" \
  && echo "OK: receiver PDF parsed (chunks + image extracted)" \
  || { echo "FAIL: receiver upload response missing expected fields" >&2; exit 1; }

echo "== Calling /generate =="
GEN_HTTP_CODE=$(curl -s -o /tmp/marketing-app-generate.json -w "%{http_code}" -X POST "http://localhost:$PORT/generate" \
  -H "Content-Type: application/json" \
  -d '{"sender_company":"NexusVisionAI","receiver_company":"ApexGlobalLogistics","prompt":"Pitch NexusVision computer vision for reducing Apex manual rescan costs."}')

if [ "$GEN_HTTP_CODE" = "200" ]; then
  echo "OK: article generated (GEMINI_API_KEY was configured)"
  python3 -m json.tool < /tmp/marketing-app-generate.json
elif [ "$GEN_HTTP_CODE" = "503" ] && grep -q "GEMINI_API_KEY is not configured" /tmp/marketing-app-generate.json; then
  echo "OK (expected without a key): /generate correctly reports GEMINI_API_KEY is not configured."
  echo "   Set it in .env and re-run this script to see a real generated article."
else
  echo "FAIL: /generate returned unexpected HTTP $GEN_HTTP_CODE:" >&2
  cat /tmp/marketing-app-generate.json >&2
  exit 1
fi

echo "== Smoke test passed =="
