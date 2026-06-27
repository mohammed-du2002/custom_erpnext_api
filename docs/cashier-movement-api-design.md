# Cashier Movement API — Design Specification

**Status:** Production (Phase 1 + Phase 2 GL optional)  
**SRS reference:** §1.4 — POS → ERP data flow (`حركات الكاشير`)  
**App:** `custom_erpnext`  
**Consumers:** Flutter POS → Laravel Middleware → ERPNext

---

## 1. Purpose

The SRS defines **Cashier Movements** as a separate push stream from POS to ERP, distinct from:

| Existing flow | What it covers |
|---|---|
| `sync_sales_invoices` | Sales + returns (revenue transactions) |
| `sync_daily_sales_summaries` | End-of-day aggregates (totals, variance) |

**Cashier movements** capture **cash-drawer lifecycle events** that are not sales invoices:

- Shift open / close (opening & closing float)
- Cash in / cash out (paid-in, paid-out, safe drop)
- Float adjustments and manager approvals
- Petty cash and bank deposit references

Without this API, cashier activity is only inferred from `cashier` + `shift_id` on Sales Invoices and summary fields on Daily Sales Summary — which is insufficient for audit trails and variance investigation (SRS §8.4: *معالجة الفروقات عند اغلاق اليومية*).

---

## 2. Architecture placement

```
Flutter POS (SQLite)
    │  offline queue: cashier_movements[]
    ▼
Laravel Sync Engine
    │  POST sync_cashier_movements (batch, retry, dead-letter)
    ▼
ERPNext custom_erpnext
    │  Cashier Movement DocType (+ POS Cashier Shift header)
    ▼
Reports / Daily Sales Summary reconciliation (optional GL in Phase 2)
```

**Design principles** (aligned with existing push APIs):

- Middleware token auth + optional HMAC signing (`middleware_api` decorator)
- Idempotent via `offline_movement_id` (same pattern as `offline_invoice_id`)
- Branch + device ownership validation
- Batch processing with `frappe.enqueue` when count > threshold
- Request UUID tracking via `request_id` / `X-Request-ID`
- No ERPNext core modifications

---

## 3. Data model

### 3.1 DocType: `POS Cashier Shift` (header)

Represents one cashier session on one device. Created or updated automatically from `Shift Open` / `Shift Close` movements.

| Field | Type | Notes |
|---|---|---|
| `naming_series` | Select | `PCS-{branch}-.` (branch naming) |
| `offline_shift_id` | Data | **Unique.** POS-generated idempotency key |
| `shift_id` | Data | Human-readable shift id (matches Sales Invoice `shift_id`) |
| `company` | Link → Company | Required |
| `branch` | Link → Company Branch | Required, validated |
| `pos_device` | Link → POS Device | Required |
| `cashier` | Link → User | Required |
| `status` | Select | `Open` / `Closed` / `Synced` |
| `opening_datetime` | Datetime | From Shift Open movement |
| `closing_datetime` | Datetime | From Shift Close movement |
| `opening_cash` | Currency | Declared float at open |
| `expected_cash` | Currency | Computed: opening + cash_in − cash_out − drops |
| `closing_cash` | Currency | Declared count at close |
| `variance` | Currency | `closing_cash − expected_cash` |
| `daily_sales_summary` | Link → Daily Sales Summary | Set when day closes (optional) |
| `sync_status` | Select | `Pending` / `Synced` / `Failed` |
| `sync_log` | Small Text | Last sync message |
| `sync_time` | Datetime | Read-only |

**Indexes:** `offline_shift_id` (unique), `(branch, shift_id)`, `(pos_device, status)`.

### 3.2 DocType: `Cashier Movement` (atomic event)

Each offline event from POS maps 1:1 to one document.

| Field | Type | Notes |
|---|---|---|
| `naming_series` | Select | `CMV-{branch}-.` |
| `offline_movement_id` | Data | **Unique.** Primary idempotency key |
| `movement_type` | Select | See §3.3 |
| `movement_datetime` | Datetime | POS event time (not sync time) |
| `company` | Link → Company | Required |
| `branch` | Link → Company Branch | Required |
| `pos_device` | Link → POS Device | Required |
| `cashier` | Link → User | Required |
| `offline_shift_id` | Data | Links to shift header |
| `shift_id` | Data | Denormalized for reporting |
| `amount` | Currency | Absolute value; direction from `movement_type` |
| `direction` | Select | `In` / `Out` / `Neutral` (derived, stored for queries) |
| `opening_balance` | Currency | Only for `Shift Open` |
| `closing_balance` | Currency | Only for `Shift Close` |
| `mode_of_payment` | Link → Mode of Payment | Optional (e.g. Cash) |
| `reference_doctype` | Data | Optional: `Sales Invoice`, etc. |
| `reference_name` | Dynamic Link | Optional linked document |
| `offline_reference_id` | Data | e.g. `offline_invoice_id` for refund-related movement |
| `reason` | Small Text | Required for Cash Out, Float Adjustment |
| `approved_by` | Link → User | Required when amount > manager threshold |
| `remarks` | Small Text | Optional |
| `pos_cashier_shift` | Link → POS Cashier Shift | Set on insert |
| `sync_status` | Select | `Pending` / `Synced` / `Failed` |
| `sync_log` | Small Text | |
| `request_id` | Data | Middleware request UUID |

### 3.3 Movement types

| `movement_type` | `direction` | Description | Required extra fields |
|---|---|---|---|
| `Shift Open` | Neutral | Start cashier session | `opening_balance`, `offline_shift_id` |
| `Shift Close` | Neutral | End session, declare count | `closing_balance`, `offline_shift_id` |
| `Cash In` | In | Add cash to drawer | `amount`, `reason` |
| `Cash Out` | Out | Remove cash (non-sale) | `amount`, `reason` |
| `Safe Drop` | Out | Transfer excess to safe | `amount` |
| `Petty Cash` | Out | Petty cash expense | `amount`, `reason` |
| `Float Adjustment` | In/Out | Manager correction | `amount`, `reason`, `approved_by` |
| `Bank Deposit` | Out | Deposit slip reference | `amount`, `remarks` |
| `Change Fund` | In/Out | Change fund top-up or return | `amount`, `reason` |

**Sign convention:** POS always sends **positive** `amount`; server derives `direction` from `movement_type`. For `Float Adjustment` and `Change Fund`, include `direction` explicitly in payload (`"in"` or `"out"`).

### 3.4 Why not ERPNext `POS Opening Entry` / `POS Closing Entry`?

Standard ERPNext POS Opening/Closing Entry is built for the **desk POS** workflow (live session, invoice aggregation on close). This retail stack uses:

- Offline-first Flutter POS
- Custom `POS Device` + `Daily Sales Summary`
- Middleware batch sync with idempotency keys

Mapping to standard POS Opening/Closing Entry would fight the offline model and couple sync to ERPNext desk POS behavior. **Phase 2** may optionally post a Journal Entry on shift close; Phase 1 stores movements in custom DocTypes only.

---

## 4. API specification

### 4.1 Endpoint

```
POST /api/method/custom_erpnext.api.v1.push.sync_cashier_movements
```

| Property | Value |
|---|---|
| Auth | `@middleware_api` (token + optional HMAC) |
| Content-Type | `application/json` |
| Idempotency | Per `offline_movement_id` |
| Batch limit | 50 movements per request (configurable) |
| Queue threshold | > 20 movements → `frappe.enqueue` on `long` queue |

### 4.2 Request body

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "movements": [
    {
      "offline_movement_id": "CMV-POS-2026-00001",
      "movement_type": "Shift Open",
      "movement_datetime": "2026-06-27T08:00:00",
      "company": "tsc",
      "branch": "BR1",
      "pos_device": "POS-BR1-01",
      "cashier": "cashier.br1@retail.local",
      "offline_shift_id": "SHIFT-POS-2026-00042",
      "shift_id": "SHIFT-2026-00042",
      "opening_balance": 500.00,
      "mode_of_payment": "Cash",
      "remarks": "Morning float"
    },
    {
      "offline_movement_id": "CMV-POS-2026-00002",
      "movement_type": "Cash In",
      "movement_datetime": "2026-06-27T10:30:00",
      "company": "tsc",
      "branch": "BR1",
      "pos_device": "POS-BR1-01",
      "cashier": "cashier.br1@retail.local",
      "offline_shift_id": "SHIFT-POS-2026-00042",
      "shift_id": "SHIFT-2026-00042",
      "amount": 200.00,
      "reason": "Change fund top-up",
      "approved_by": "manager.br1@retail.local"
    },
    {
      "offline_movement_id": "CMV-POS-2026-00003",
      "movement_type": "Safe Drop",
      "movement_datetime": "2026-06-27T14:00:00",
      "company": "tsc",
      "branch": "BR1",
      "pos_device": "POS-BR1-01",
      "cashier": "cashier.br1@retail.local",
      "offline_shift_id": "SHIFT-POS-2026-00042",
      "shift_id": "SHIFT-2026-00042",
      "amount": 1000.00,
      "remarks": "Mid-day safe drop"
    },
    {
      "offline_movement_id": "CMV-POS-2026-00004",
      "movement_type": "Shift Close",
      "movement_datetime": "2026-06-27T18:00:00",
      "company": "tsc",
      "branch": "BR1",
      "pos_device": "POS-BR1-01",
      "cashier": "cashier.br1@retail.local",
      "offline_shift_id": "SHIFT-POS-2026-00042",
      "shift_id": "SHIFT-2026-00042",
      "closing_balance": 850.00,
      "remarks": "End of shift count"
    }
  ]
}
```

### 4.3 Response body

```json
{
  "message": {
    "success": true,
    "data": {
      "queued": false,
      "total": 4,
      "success_count": 4,
      "failed_count": 0,
      "results": [
        {
          "offline_movement_id": "CMV-POS-2026-00001",
          "cashier_movement": "CMV-BR1-.00001",
          "pos_cashier_shift": "PCS-BR1-.00001",
          "status": "success",
          "idempotent": false,
          "sync_status": "Synced"
        },
        {
          "offline_movement_id": "CMV-POS-2026-00002",
          "cashier_movement": "CMV-BR1-.00002",
          "pos_cashier_shift": "PCS-BR1-.00001",
          "status": "success",
          "idempotent": false,
          "sync_status": "Synced"
        }
      ]
    },
    "meta": {
      "request_id": "550e8400-e29b-41d4-a716-446655440000"
    }
  }
}
```

**Idempotent replay** (duplicate `offline_movement_id`):

```json
{
  "offline_movement_id": "CMV-POS-2026-00001",
  "cashier_movement": "CMV-BR1-.00001",
  "status": "success",
  "idempotent": true,
  "sync_status": "Synced"
}
```

### 4.4 Validation rules

| Rule | Error |
|---|---|
| `movements` required, non-empty array | 400 |
| Each movement must have `offline_movement_id` | 400 |
| `movement_type` in allowed set (§3.3) | 400 |
| `company`, `branch`, `pos_device`, `cashier` required | 400 |
| `branch` must pass `validate_branch_access` | 403 |
| `pos_device` must exist and belong to `branch` | 400 |
| `cashier` must exist with `pos_access = 1` | 400 |
| `offline_shift_id` required for all types | 400 |
| `Shift Open`: only one open shift per `offline_shift_id` | 409 |
| `Shift Close`: shift must exist; cannot close twice | 409 |
| Mid-shift movements: shift must be `Open` | 409 |
| `Cash Out` / `Petty Cash` / `Float Adjustment`: `reason` required | 400 |
| `Float Adjustment` above branch threshold: `approved_by` required | 400 |
| `approved_by` must have branch manager role | 403 |
| `movement_datetime` not in future (> 5 min skew) | 400 |
| Duplicate `offline_movement_id` in same batch | 400 |

### 4.5 Shift header side effects

On each successful movement, the service updates `POS Cashier Shift`:

| Event | Shift update |
|---|---|
| `Shift Open` | Create shift (`status=Open`), set `opening_cash`, `opening_datetime` |
| `Cash In` / `Out` / `Safe Drop` / etc. | Recompute `expected_cash` |
| `Shift Close` | Set `closing_cash`, `closing_datetime`, `variance`, `status=Closed` |

**Expected cash formula:**

```
expected_cash = opening_cash
              + SUM(Cash In, Change Fund In, Float Adjustment In)
              - SUM(Cash Out, Safe Drop, Petty Cash, Bank Deposit, Change Fund Out, Float Adjustment Out)
```

Sales invoice cash is **not** double-counted here — it flows through `sync_sales_invoices`. The shift `expected_cash` is drawer-level; reconciliation against `Daily Sales Summary.cash_sales` is a **reporting concern** (see §6).

---

## 5. Laravel SDK addition

### 5.1 `PushApi.php`

```php
public function syncCashierMovements(array $movements, ?string $requestId = null): array
{
    return $this->client->push('sync_cashier_movements', [
        'movements' => $movements,
        'request_id' => $requestId,
    ], $requestId);
}
```

### 5.2 Laravel queue job (recommended)

```php
// App\Jobs\PushCashierMovementsToErp
// - chunk movements (50)
// - retry 3x with backoff
// - dead-letter failed offline_movement_ids
// - mark local SQLite rows synced on success
```

### 5.3 Sync Configuration (ERPNext bootstrap)

Add to `DEFAULT_SYNC_CONFIGS` in `laravel_integration.py`:

```python
{
    "config_name": "Push Cashier Movements",
    "sync_type": "Push (POS→ERP)",
    "entity": "All",
    "frequency": "Manual",
    "batch_size": 50,
    "timeout_seconds": 60,
    "retry_attempts": 5,
}
```

Extend `Sync Configuration.entity` options to include `Cashier Movement` (migration patch).

---

## 6. Relationship to Daily Sales Summary

```
┌─────────────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│  Cashier Movements  │     │   POS Cashier Shift   │     │ Daily Sales Summary │
│  (event stream)     │────▶│   (per shift)         │────▶│ (per device/day)    │
└─────────────────────┘     └──────────────────────┘     └─────────────────────┘
   Shift Open/Close            variance per shift            opening/closing cash
   Cash In/Out                  links via shift_id            aggregates all shifts
```

| Concern | Source of truth |
|---|---|
| Individual drawer events | `Cashier Movement` |
| Per-shift variance | `POS Cashier Shift.variance` |
| Day-level totals & tax | `Daily Sales Summary` (existing API) |
| Revenue transactions | `Sales Invoice` (existing API) |

**Reconciliation report** (Phase 1 — query report, no new API):

```
Daily Sales Summary.closing_cash
  ≈ last Shift Close.closing_balance for that device/day
  ≈ opening_cash + cash_sales − cash_returns ± net movements
```

SRS §8.4 variance handling uses all three layers.

---

## 7. Flutter POS offline contract

### 7.1 SQLite table: `cashier_movements`

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Local autoincrement |
| `offline_movement_id` | TEXT UNIQUE | Generated at creation |
| `offline_shift_id` | TEXT | |
| `movement_type` | TEXT | |
| `payload_json` | TEXT | Full API payload |
| `movement_datetime` | TEXT ISO8601 | |
| `sync_status` | TEXT | `pending` / `synced` / `failed` |
| `sync_attempts` | INTEGER | |
| `last_error` | TEXT | |
| `created_at` | TEXT | |

### 7.2 Local ID generation

```
offline_movement_id = "CMV-{device_id}-{local_seq}"
offline_shift_id    = "SHIFT-{device_id}-{shift_seq}"
shift_id            = "SHIFT-{YYYYMMDD}-{cashier_number}-{seq}"  // display / SI link
```

### 7.3 Sync ordering

1. Movements sync **in `movement_datetime` order** per shift (Laravel preserves order in batch).
2. `Shift Open` must sync before mid-shift movements (POS enforces locally).
3. `Shift Close` syncs after last sale of shift (or with end-of-shift batch).
4. `sync_daily_sales_summaries` may run after all shift closes for the day.

---

## 8. Implementation map (Phase 1)

| File | Responsibility |
|---|---|
| `doctype/pos_cashier_shift/` | Shift header DocType |
| `doctype/cashier_movement/` | Movement DocType |
| `services/cashier_movement_sync_service.py` | Business logic, idempotency, shift updates |
| `api/v1/push.py` | `sync_cashier_movements` whitelisted method |
| `services/naming_series_service.py` | Add `PCS-` and `CMV-` templates |
| `setup/laravel_integration.py` | Sync config bootstrap |
| `setup/integration_tests.py` | HTTP test cases |
| `integrations/laravel/src/Services/PushApi.php` | Laravel client method |
| `docs/postman/custom_erpnext-push-api.postman_collection.json` | Example request |
| `patches/v1_0/add_cashier_movement_sync_config.py` | Migration for existing sites |

### 8.1 Service skeleton

```python
# cashier_movement_sync_service.py (planned)

BATCH_ENQUEUE_THRESHOLD = 20

def sync_cashier_movements(movements, request_id=None):
    if len(movements) > BATCH_ENQUEUE_THRESHOLD:
        job = frappe.enqueue(
            "custom_erpnext.services.cashier_movement_sync_service.process_movement_batch",
            queue="long",
            movements=movements,
            request_id=request_id,
            timeout=1800,
        )
        return {"queued": True, "count": len(movements), "job_id": job.id}
    return process_movement_batch(movements, request_id=request_id)


def process_movement_batch(movements, request_id=None):
    results = []
    for data in sorted(movements, key=lambda m: m.get("movement_datetime") or ""):
        try:
            results.append(create_or_update_cashier_movement(data, request_id))
        except Exception as err:
            frappe.log_error(title="Cashier Movement Sync Failed", message=frappe.get_traceback())
            results.append({
                "offline_movement_id": data.get("offline_movement_id"),
                "status": "failed",
                "error": str(err),
            })
    return {"queued": False, "results": results, ...}
```

---

## 9. Phase 2 (optional — accounting)

When `POS Cashier Shift` closes with non-zero variance or on manager approval:

| Trigger | ERP action |
|---|---|
| Shift Close + variance ≠ 0 | Draft Journal Entry: Cash Short/Over account |
| Bank Deposit movement | Journal Entry: Cash → Bank |
| Petty Cash | Journal Entry: Expense → Cash |

Controlled by **Retail Settings** flag `post_cashier_movement_gl` (default off). No GL in Phase 1.

---

## 10. Security & audit

- All writes via middleware user; `ignore_permissions` only inside `middleware_sync_context`
- `approved_by` validated against `User Discount Profile.is_branch_manager` or role
- `User Activity Monitor` hook on insert (align with SRS §9)
- Rate limit: existing middleware rate limiter applies
- Never expose API secrets in movement payloads

---

## 11. Test plan

| # | Scenario | Expected |
|---|---|---|
| 1 | Shift Open → Cash In → Shift Close | Shift `Open` → `Closed`, 3 movement docs |
| 2 | Duplicate `offline_movement_id` | `idempotent: true`, no duplicate doc |
| 3 | Shift Close without Shift Open | 409 error |
| 4 | Movement on wrong branch/device | 400 validation error |
| 5 | Cash Out without `reason` | 400 validation error |
| 6 | Batch of 25 movements | Queued job, all processed |
| 7 | `shift_id` matches Sales Invoice | Cross-report join works |
| 8 | Link to Daily Sales Summary | Optional `daily_sales_summary` set on day close job |

Run via:

```bash
bench --site SITE execute custom_erpnext.setup.integration_tests.run_laravel_integration_tests
```

---

## 12. SRS compliance checklist

| SRS requirement | Covered by |
|---|---|
| POS → ERP cashier movements | `sync_cashier_movements` |
| Offline-first / idempotent sync | `offline_movement_id` |
| Shift tracking | `POS Cashier Shift` + `shift_id` on SI |
| Daily closing variance | Reconciliation with `Daily Sales Summary` |
| Manager approval on sensitive ops | `approved_by` validation |
| Audit trail | `Cashier Movement` + `User Activity Monitor` |

---

## 13. Open decisions

| # | Question | Recommendation |
|---|---|---|
| 1 | Single endpoint vs split (`sync_shifts` + `sync_movements`) | **Single endpoint** — simpler POS offline queue |
| 2 | Pull shift status back to POS? | Phase 2: `pull_cashier_shifts` for manager dashboard only |
| 3 | Link movement to refund invoice? | Optional `offline_reference_id` → resolve after SI sync |
| 4 | Multi-currency drawers? | Defer — assume company default currency in Phase 1 |

---

*Document version: 1.0 — 2026-06-27*
