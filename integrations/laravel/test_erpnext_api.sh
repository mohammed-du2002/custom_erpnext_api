#!/usr/bin/env bash
# Quick ERPNext middleware API test from shell (no Laravel required).
# Usage: ./test_erpnext_api.sh KEY SECRET [BRANCH]

set -euo pipefail

BASE_URL="${ERPNEXT_BASE_URL:-http://tsc.localhost}"
API_KEY="${1:?API key required}"
API_SECRET="${2:?API secret required}"
BRANCH="${3:-BR1}"
METHOD="${4:-custom_erpnext.api.v1.pull.health_check}"
BODY="${5:-{}}"

TS=$(date +%s)
SIG=$(printf '%s.%s' "$TS" "$BODY" | openssl dgst -sha256 -hmac "$API_SECRET" | awk '{print $2}')

echo "→ POST $METHOD"
curl -sS -X POST "$BASE_URL/api/method/$METHOD" \
  -H "Authorization: token ${API_KEY}:${API_SECRET}" \
  -H "Content-Type: application/json" \
  -H "X-Timestamp: $TS" \
  -H "X-Signature: $SIG" \
  -H "X-Request-ID: $(uuidgen 2>/dev/null || cat /proc/sys/kernel/random/uuid)" \
  -d "$BODY" | python3 -m json.tool

echo ""
echo "→ Pull branches"
BODY='{}'
TS=$(date +%s)
SIG=$(printf '%s.%s' "$TS" "$BODY" | openssl dgst -sha256 -hmac "$API_SECRET" | awk '{print $2}')
curl -sS -X POST "$BASE_URL/api/method/custom_erpnext.api.v1.pull.pull_branches" \
  -H "Authorization: token ${API_KEY}:${API_SECRET}" \
  -H "Content-Type: application/json" \
  -H "X-Timestamp: $TS" \
  -H "X-Signature: $SIG" \
  -d "$BODY" | python3 -m json.tool

echo ""
echo "→ POS items for branch $BRANCH"
BODY="{\"branch\":\"$BRANCH\",\"page\":1,\"page_size\":5}"
TS=$(date +%s)
SIG=$(printf '%s.%s' "$TS" "$BODY" | openssl dgst -sha256 -hmac "$API_SECRET" | awk '{print $2}')
curl -sS -X POST "$BASE_URL/api/method/custom_erpnext.api.v1.pull.get_items_for_pos" \
  -H "Authorization: token ${API_KEY}:${API_SECRET}" \
  -H "Content-Type: application/json" \
  -H "X-Timestamp: $TS" \
  -H "X-Signature: $SIG" \
  -d "$BODY" | python3 -m json.tool
