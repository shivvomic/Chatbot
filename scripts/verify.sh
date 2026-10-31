#!/usr/bin/env bash
# End-to-end check: lint, tests, fast eval, then start the API and probe it.
# Usage: scripts/verify.sh    (needs .env with API_KEYS and an LLM key; indexes built)
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
PORT="${PORT:-8765}"

echo "== lint";        .venv/bin/ruff check .
echo "== tests";       $PY -m pytest -q
echo "== fast eval";   $PY -m eval.run_eval --fast > /dev/null && echo "eval/REPORT.md updated"

# First admin key from API_KEYS (read via config so .env parsing matches the app).
ADMIN_KEY="$($PY -c 'from ui.api_client import role_keys; print(role_keys().get("admin", ""))')"
CUSTOMER_KEY="$($PY -c 'from ui.api_client import role_keys; print(role_keys().get("customer", ""))')"
[ -n "$ADMIN_KEY" ] && [ -n "$CUSTOMER_KEY" ] || { echo "API_KEYS needs a customer and an admin key"; exit 1; }

echo "== start API on :$PORT"
.venv/bin/uvicorn app.api.main:app --port "$PORT" --log-level warning > /dev/null 2>&1 &
API_PID=$!
trap 'kill $API_PID 2>/dev/null || true' EXIT
for _ in $(seq 1 60); do curl -sf "http://127.0.0.1:$PORT/health" > /dev/null && break; sleep 1; done
curl -sf "http://127.0.0.1:$PORT/health" && echo

ask() {  # ask <expected-status> <api-key> <question>
  local got
  got="$(curl -s -X POST "http://127.0.0.1:$PORT/ask" -H "X-API-Key: $2" -H 'Content-Type: application/json' \
        -d "{\"question\": \"$3\"}" | $PY -c 'import json,sys; print(json.load(sys.stdin).get("status"))')"
  printf '%-22s expected %-20s got %s\n' "$3" "$1" "$got"
  [ "$got" = "$1" ] || FAILED=1
}
FAILED=0
ask answered            "$CUSTOMER_KEY" "How many custom ticket fields can a workspace have?"
ask conflict            "$CUSTOMER_KEY" "What is the maximum attachment size?"
ask needs_clarification "$CUSTOMER_KEY" "What is the limit?"
ask not_found           "$CUSTOMER_KEY" "What does webhook error code WH-500 mean?"
ask refused             "$CUSTOMER_KEY" "How long does a database failover to the replica region take?"
[ "$FAILED" = 0 ] && echo "verify: OK" || { echo "verify: status mismatch"; exit 1; }
