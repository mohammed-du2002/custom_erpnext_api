# ERPNext ↔ Laravel Middleware Integration

PHP client and setup scripts for syncing **Flutter POS ↔ Laravel ↔ ERPNext**.

## Architecture

```
Flutter POS  →  Laravel (Sync Engine)  →  ERPNext (custom_erpnext API)
                     ↑                           ↓
                     └──── Pull master data ──────┘
                     └──── Push sales/stock ──────┘
```

## 1. ERPNext setup

Run on the Frappe bench:

```bash
bench --site tsc.localhost execute custom_erpnext.setup.laravel_integration.setup_laravel_integration
```

This creates:

- User: `middleware@laravel.local`
- API key + secret (printed in output)
- **API Integration Settings** → Laravel Middleware

Copy the printed `.env` snippet into your Laravel project.

## 2. Laravel installation

### Option A — Copy files into your Laravel app

```bash
# From frappe-bench root
cp -r apps/custom_erpnext/integrations/laravel/src/* /path/to/laravel/app/Services/ErpNext/
cp apps/custom_erpnext/integrations/laravel/config/erpnext.php /path/to/laravel/config/
cp apps/custom_erpnext/integrations/laravel/examples/ErpNextServiceProvider.php /path/to/laravel/app/Providers/
cp apps/custom_erpnext/integrations/laravel/examples/ErpNextSyncTest.php /path/to/laravel/app/Console/Commands/
```

Adjust namespaces to match your app (`App\Services\ErpNext\...`) or register PSR-4 autoload for `CustomErpnext\Laravel\`.

### Option B — PSR-4 in composer.json

```json
"autoload": {
  "psr-4": {
    "CustomErpnext\\Laravel\\": "integrations/erpnext/src/"
  }
}
```

## 3. Laravel `.env`

```env
ERPNEXT_BASE_URL=http://tsc.localhost
ERPNEXT_API_KEY=your_api_key
ERPNEXT_API_SECRET=your_api_secret
ERPNEXT_SIGN_REQUESTS=true
ERPNEXT_TIMEOUT=30
ERPNEXT_RETRY_TIMES=3
ERPNEXT_RETRY_SLEEP_MS=500
```

## 4. Test connectivity

```bash
php artisan erpnext:sync-test --branch=BR1
php artisan erpnext:sync-test --branch=BR1 --push
```

## API endpoints

### Pull (ERP → Laravel)

| Method | Frappe path | Purpose |
|--------|-------------|---------|
| `healthCheck()` | `pull.health_check` | Connectivity |
| `pullBranches()` | `pull.pull_branches` | Company branches |
| `getItemsForPos($branch)` | `pull.get_items_for_pos` | POS catalog |
| `pullItemPrices()` | `pull.pull_item_prices` | Price sync |
| `pullCustomers()` | `pull.pull_customers` | Customers |
| `pullWarehouses()` | `pull.pull_warehouses` | Warehouses |
| `pullStock()` | `pull.pull_stock` | Stock levels |
| `pullPromotions()` | `pull.pull_promotions` | Promotions |
| `pullPosDevices()` | `pull.pull_pos_devices` | POS devices |
| `pullTaxTemplates()` | `pull.pull_tax_templates` | Tax templates |

### Push (Laravel → ERP)

| Method | Frappe path | Purpose |
|--------|-------------|---------|
| `syncSalesInvoices($invoices)` | `push.sync_sales_invoices` | Offline SI sync |
| `syncDailySalesSummaries($summaries)` | `push.sync_daily_sales_summaries` | Daily closing |
| `updateStockQuantities($updates)` | `push.update_stock_quantities` | Stock reconciliation |
| `updatePosDeviceStatus()` | `push.update_pos_device_status` | Device heartbeat |

## Authentication

All requests use Frappe token auth:

```
Authorization: token {api_key}:{api_secret}
```

When `ERPNEXT_SIGN_REQUESTS=true`, POST bodies are signed:

```
X-Timestamp: {unix_timestamp}
X-Signature: HMAC-SHA256("{timestamp}.{raw_json_body}", api_secret)
X-Request-ID: {uuid}
```

## Push payload examples

### Sales Invoice (idempotent via `offline_invoice_id`)

```json
{
  "invoices": [{
    "offline_invoice_id": "POS-2026-00042",
    "company": "tsc",
    "customer": "Test Retail Customer",
    "branch": "BR1",
    "warehouse": "Stores - T",
    "posting_date": "2026-06-06",
    "is_pos": 1,
    "submit": 1,
    "items": [{
      "item_code": "TEST-RETAIL-ITEM",
      "qty": 2,
      "rate": 100
    }],
    "payments": [{
      "mode_of_payment": "Cash",
      "amount": 200
    }]
  }]
}
```

### Daily Sales Summary

```json
{
  "summaries": [{
    "summary_date": "2026-06-06",
    "branch": "BR1",
    "pos_device": "POS-BR1-01",
    "total_sales": 5000,
    "net_sales": 4800,
    "transaction_count": 42
  }]
}
```

## Response format

```json
{
  "success": true,
  "data": { },
  "errors": [],
  "meta": {
    "page": 1,
    "page_size": 100,
    "total": 250,
    "request_id": "uuid"
  }
}
```

## Incremental sync pattern (Laravel job)

```php
$pull = app(PullApi::class);
$cursor = SyncCursor::for('items', $branchId);
$response = $pull->getItemsForPos(
    branch: $branchCode,
    modifiedFrom: $cursor->last_synced_at,
    page: $cursor->page,
);
// Store items, advance cursor from meta.total_pages
```

## Error handling

```php
use CustomErpnext\Laravel\ErpNextException;

try {
    $push->syncSalesInvoices($batch, $requestId);
} catch (ErpNextException $e) {
    // $e->code: RATE_LIMIT | AUTH_ERROR | VALIDATION_ERROR | ...
    if ($e->code === 'RATE_LIMIT') {
        // re-queue with backoff
    }
}
```

## Shell test (without Laravel)

```bash
# After setup_laravel_integration
curl -s -X POST "http://tsc.localhost/api/method/custom_erpnext.api.v1.pull.health_check" \
  -H "Authorization: token KEY:SECRET" \
  -H "Content-Type: application/json"
```
