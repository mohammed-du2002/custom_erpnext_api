#!/usr/bin/env bash
# Test custom_erpnext push APIs with curl + canonical HMAC signing (SEC-04).
#
# Usage:
#   export ERPNEXT_BASE_URL="http://tsc.localhost:8000"
#   export ERPNEXT_API_KEY="your_key"
#   export ERPNEXT_API_SECRET="your_secret"
#   export ERPNEXT_HOST="tsc.localhost"   # optional, Host header
#   ./test-push-api.sh invoice
#   ./test-push-api.sh cashier
#
# Get credentials:
#   bench --site tsc.localhost execute custom_erpnext.setup.laravel_integration.get_middleware_api_credentials

set -euo pipefail

BASE_URL="${ERPNEXT_BASE_URL:-http://127.0.0.1:8000}"
API_KEY="${ERPNEXT_API_KEY:?Set ERPNEXT_API_KEY}"
API_SECRET="${ERPNEXT_API_SECRET:?Set ERPNEXT_API_SECRET}"
HOST="${ERPNEXT_HOST:-tsc.localhost}"
ACTION="${1:-invoice}"

uuid() {
	if command -v uuidgen >/dev/null 2>&1; then
		uuidgen | tr '[:upper:]' '[:lower:]'
	else
		cat /proc/sys/kernel/random/uuid 2>/dev/null || python3 -c 'import uuid; print(uuid.uuid4())'
	fi
}

sign_and_post() {
	local method_path="$1"
	local body="$2"
	local path="/api/method/${method_path}"
	local url="${BASE_URL%/}${path}"
	local ts rid msg sig

	ts="$(date +%s)"
	rid="$(uuid)"
	# Canonical message: METHOD \n PATH \n QUERY \n TIMESTAMP \n REQUEST_ID \n BODY
	msg="$(printf 'POST\n%s\n\n%s\n%s\n%s' "$path" "$ts" "$rid" "$body")"
	sig="$(printf '%s' "$msg" | openssl dgst -sha256 -hmac "$API_SECRET" | awk '{print $NF}')"

	echo "POST ${url}"
	echo "X-Request-ID: ${rid}"
	echo "X-Timestamp:  ${ts}"
	echo "---"

	curl -sS -w "\n\nHTTP_STATUS:%{http_code}\n" \
		-X POST "$url" \
		-H "Host: ${HOST}" \
		-H "Authorization: token ${API_KEY}:${API_SECRET}" \
		-H "Content-Type: application/json" \
		-H "Accept: application/json" \
		-H "X-Request-ID: ${rid}" \
		-H "X-Timestamp: ${ts}" \
		-H "X-Signature: ${sig}" \
		--data "$body"
	echo
}

case "$ACTION" in
invoice)
	offline_id="POS-CURL-$(uuid | cut -c1-8)"
	body="$(python3 - <<PY
import json, uuid
print(json.dumps({
    "request_id": str(uuid.uuid4()),
    "invoices": [{
        "offline_invoice_id": "${offline_id}",
        "company": "tsc",
        "customer": "Test Retail Customer",
        "branch": "BR1",
        "warehouse": "Stores - T",
        "pos_device": "TEST-POS-BR1",
        "cashier": "middleware@laravel.local",
        "posting_date": "2026-06-27",
        "is_pos": 1,
        "submit": 1,
        "items": [{"item_code": "RET-BREAD-WHITE", "qty": 1, "rate": 10}],
        "payments": [{"mode_of_payment": "Cash", "amount": 11.5, "payment_provider": "Cash"}],
        "remarks": "curl test",
    }],
}, separators=(",", ":")))
PY
)"
	sign_and_post "custom_erpnext.api.v1.push.sync_sales_invoices" "$body"
	;;
cashier)
	suffix="$(uuid | cut -c1-8)"
	shift_id="SHIFT-CURL-${suffix}"
	body="$(python3 - <<PY
import json, uuid
from datetime import datetime, timedelta
now = datetime.now()
fmt = lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%S")
print(json.dumps({
    "request_id": str(uuid.uuid4()),
    "movements": [
        {
            "offline_movement_id": "CMV-OPEN-${suffix}",
            "movement_type": "Shift Open",
            "movement_datetime": fmt(now - timedelta(hours=2)),
            "company": "tsc",
            "branch": "BR1",
            "pos_device": "TEST-POS-BR1",
            "cashier": "middleware@laravel.local",
            "offline_shift_id": "${shift_id}",
            "shift_id": "${shift_id}",
            "opening_balance": 500,
        },
        {
            "offline_movement_id": "CMV-CLOSE-${suffix}",
            "movement_type": "Shift Close",
            "movement_datetime": fmt(now - timedelta(minutes=5)),
            "company": "tsc",
            "branch": "BR1",
            "pos_device": "TEST-POS-BR1",
            "cashier": "middleware@laravel.local",
            "offline_shift_id": "${shift_id}",
            "shift_id": "${shift_id}",
            "closing_balance": 600,
        },
    ],
}, separators=(",", ":")))
PY
)"
	sign_and_post "custom_erpnext.api.v1.push.sync_cashier_movements" "$body"
	;;
*)
	echo "Usage: $0 [invoice|cashier]" >&2
	exit 1
	;;
esac
