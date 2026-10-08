#!/bin/bash
# Demo requests against the local backend API.
# 1. Start the backend:   python -m src.server   (from the project root)
# 2. Run:                 bash examples/sample-requests.sh
#
# If WEBHOOK_SECRET is set in your environment, export it first so the
# header below matches:  export WEBHOOK_SECRET=your-secret

BASE="${BASE_URL:-http://127.0.0.1:8000}"
AUTH=()
if [ -n "$WEBHOOK_SECRET" ]; then
  AUTH=(-H "X-Webhook-Secret: $WEBHOOK_SECRET")
fi

echo "== Health =="
curl -s "$BASE/health"; echo; echo

echo "== 1. FAQ =="
curl -s -X POST "$BASE/api/handle" "${AUTH[@]}" \
  -H 'Content-Type: application/json' \
  -d '{"message": "What is your return policy?"}' | head -c 600; echo; echo

echo "== 2. Order status =="
curl -s -X POST "$BASE/api/handle" "${AUTH[@]}" \
  -H 'Content-Type: application/json' \
  -d '{"message": "Where is my order #1042?"}' | head -c 600; echo; echo

echo "== 3. Refund (escalates) =="
curl -s -X POST "$BASE/api/handle" "${AUTH[@]}" \
  -H 'Content-Type: application/json' \
  -d '{"message": "I want a refund for order #1043."}' | head -c 600; echo; echo

echo "== 4. Classify only =="
curl -s -X POST "$BASE/api/classify" "${AUTH[@]}" \
  -H 'Content-Type: application/json' \
  -d '{"message": "The checkout keeps crashing with an error."}'; echo; echo

echo "== 5. Mock order lookup =="
curl -s "$BASE/api/orders/1042" | head -c 400; echo
