# Production Deployment — custom_erpnext + Laravel Integration

Complete checklist to deploy `custom_erpnext` on a production Frappe/ERPNext server and connect Laravel Middleware.

---

## Architecture

```
Flutter POS  →  Laravel (Sync Engine)  →  ERPNext (custom_erpnext APIs)
                     ↑                           ↓
                     └──── Pull master data ──────┘
                     └──── Push sales/stock ──────┘
                     ↑
              Webhook (urgent item/price changes)
```

---

## Phase 1 — Server & Frappe Bench

### 1.1 Server requirements

| Component | Minimum |
|-----------|---------|
| OS | Ubuntu 22.04+ |
| RAM | 4 GB (8 GB recommended) |
| CPU | 2 cores |
| Disk | 40 GB SSD |
| Python | 3.10+ |
| MariaDB | 10.6+ |
| Redis | 6+ |
| Node | 18+ (for bench build) |

### 1.2 Install Frappe Bench (if new server)

```bash
# Follow official Frappe docs: https://frappeframework.com/docs/user/en/installation
sudo apt update && sudo apt install -y git python3-dev python3-pip redis-server mariadb-server
# ... bench init, create site
```

### 1.3 Get custom_erpnext on the server

**Option A — Git (recommended)**

```bash
cd ~/frappe-bench/apps
git clone <your-repo-url> custom_erpnext
cd ~/frappe-bench
bench get-app custom_erpnext  # if not cloned manually
bench --site your-site.com install-app custom_erpnext
```

**Option B — Copy from dev bench**

```bash
rsync -avz ./apps/custom_erpnext/ user@prod:/home/frappe/frappe-bench/apps/custom_erpnext/
ssh user@prod "cd frappe-bench && bench --site your-site.com install-app custom_erpnext"
```

### 1.4 Production site config

Edit `sites/your-site.com/site_config.json`:

```json
{
  "host_name": "https://erp.yourdomain.com",
  "developer_mode": 0,
  "maintenance_mode": 0,
  "allow_cors": "https://middleware.yourdomain.com",
  "cors_allowed_origins": ["https://middleware.yourdomain.com"]
}
```

### 1.5 Migrate & build

```bash
cd ~/frappe-bench
bench --site your-site.com migrate
bench --site your-site.com clear-cache
bench setup production frappe
sudo supervisorctl restart all
```

---

## Phase 2 — ERPNext Master Data

Before Laravel can sync, ERPNext needs:

| # | DocType | Required |
|---|---------|----------|
| 1 | Company | ✓ |
| 2 | Company Branch (BR1, BR2…) | ✓ |
| 3 | Warehouse (per branch) | ✓ |
| 4 | Items + Item Groups + Item Prices | ✓ |
| 5 | Customers | ✓ |
| 6 | Suppliers | Optional |
| 7 | POS Device (per terminal) | ✓ |
| 8 | POS Profile (per branch) | ✓ |
| 9 | Mode of Payment (Cash, Card…) | ✓ |

**Quick seed (dev/staging):**

```bash
bench --site your-site.com execute custom_erpnext.setup.retail_test_data.create_full_retail_test_data
```

---

## Phase 3 — Laravel Integration Setup (one command)

Run on production site:

```bash
bench --site your-site.com execute custom_erpnext.setup.laravel_integration.setup_production_integration \
  --kwargs "{
    'site_url': 'https://erp.yourdomain.com',
    'webhook_url': 'https://middleware.yourdomain.com/api/webhooks/erpnext',
    'laravel_api_endpoint': 'https://middleware.yourdomain.com/api/sync',
    'rate_limit_per_minute': 120
  }"
```

This creates:

### API Integration Settings

| Field | Value |
|-------|-------|
| Integration Name | Laravel Middleware |
| System | Laravel Middleware |
| Is Active | ✓ |
| Auth Type | API Key |
| Endpoint URL | `https://erp.yourdomain.com` |
| Webhook URL | Laravel webhook endpoint |
| Rate Limit | 120/min |
| API Key / Secret | Generated (printed in output) |

### Middleware API User

| Field | Value |
|-------|-------|
| Email | `middleware@laravel.local` |
| Roles | Sales User, Stock User, Accounts User, Purchase User |
| **Not** System Manager | HMAC signature enforced |
| User Permissions | All active Company Branches |

### Sync Configuration (12 records)

| Config Name | Type | Entity | Frequency |
|-------------|------|--------|-----------|
| Pull Items | Pull | Item | Every 10 Minutes |
| Pull Item Prices | Pull | Price | Every 10 Minutes |
| Pull Customers | Pull | Customer | Hourly |
| Pull Warehouses | Pull | Warehouse | Daily |
| Pull Stock | Pull | Stock | Every 10 Minutes |
| Pull Promotions | Pull | Promotion | Hourly |
| Pull Tax Templates | Pull | Tax | Daily |
| Push Sales Invoices | Push | All | Manual (Laravel queue) |
| Push Daily Summaries | Push | All | Manual |
| Urgent Item Changes | Urgent | Item | Real-time |
| Urgent Price Changes | Urgent | Price | Real-time |

> **Note:** ERPNext scheduler triggers Pull configs every 10 min (see `hooks.py`). Laravel owns actual HTTP pull/push — Sync Configuration is the **orchestration registry** + metadata for monitoring.

---

## Phase 4 — Copy credentials to Laravel

From command output, add to Laravel `.env`:

```env
ERPNEXT_BASE_URL=https://erp.yourdomain.com
ERPNEXT_API_KEY=<from output>
ERPNEXT_API_SECRET=<from output>
ERPNEXT_SIGN_REQUESTS=true
ERPNEXT_TIMEOUT=30
ERPNEXT_RETRY_TIMES=3
ERPNEXT_RETRY_SLEEP_MS=500
```

Copy PHP client from:

```
apps/custom_erpnext/integrations/laravel/
```

See `integrations/laravel/README.md` for Laravel setup.

---

## Phase 5 — Verify integration

### 5.1 ERPNext integration tests

```bash
bench --site your-site.com execute custom_erpnext.setup.integration_tests.run_laravel_integration_tests
```

Expected: **18/18 passed**

### 5.2 Shell test

```bash
./apps/custom_erpnext/integrations/laravel/test_erpnext_api.sh API_KEY API_SECRET BR1
```

### 5.3 Laravel test

```bash
php artisan erpnext:sync-test --branch=BR1
php artisan erpnext:sync-test --branch=BR1 --push
```

### 5.4 Desk verification

1. **API Integration Settings** → Laravel Middleware → Is Active ✓
2. **Sync Configuration** → 11 active records
3. **User** → `middleware@laravel.local` → API Access section shows key
4. **User Permission** → Company Branch rows for middleware user

---

## Phase 6 — Production hardening

### 6.1 HTTPS (mandatory)

```bash
# nginx + Let's Encrypt
sudo certbot --nginx -d erp.yourdomain.com
```

Ensure `host_name` in site_config uses `https://`.

### 6.2 Workers & scheduler

```bash
bench setup supervisor
bench setup nginx
sudo supervisorctl status
```

Required processes:

| Process | Purpose |
|---------|---------|
| `frappe-bench-web` | HTTP |
| `frappe-bench-workers` | Queue jobs (sync batches) |
| `frappe-bench-schedule` | Cron (every 10 min sync trigger) |

Verify scheduler in `hooks.py`:

```python
scheduler_events = {
    "cron": {"*/10 * * * *": ["custom_erpnext.tasks.run_scheduled_sync"]},
    "hourly": ["custom_erpnext.tasks.check_item_reorder"],
}
```

### 6.3 Firewall

```bash
# Allow only nginx (443) — block direct 8000/9000 from internet
sudo ufw allow 443/tcp
sudo ufw allow 22/tcp
sudo ufw enable
```

### 6.4 Secrets rotation

```bash
# Regenerate keys (updates Laravel .env too)
bench --site your-site.com execute custom_erpnext.setup.laravel_integration.setup_laravel_integration
```

### 6.5 Backups

```bash
bench --site your-site.com backup --with-files
# Add to crontab: daily backup
```

---

## Phase 7 — Laravel webhook (urgent sync)

When Item or Item Price changes in ERPNext, `sync_service.py` logs urgent sync and updates Sync Configuration timestamp. Configure webhook URL so Laravel receives push notifications.

**Laravel endpoint example:**

```
POST /api/webhooks/erpnext
Body: { "entity": "Item", "reference_name": "RET-RICE-5KG" }
```

Set in **API Integration Settings → Webhook URL**.

---

## API Reference (Laravel calls ERPNext)

**Base:** `POST https://erp.yourdomain.com/api/method/custom_erpnext.api.v1.{pull|push}.{method}`

**Headers:**

```
Authorization: token {api_key}:{api_secret}
Content-Type: application/json
X-Request-ID: {uuid}
X-Timestamp: {unix}
X-Signature: HMAC-SHA256("{method}\n{path}\n{query}\n{timestamp}\n{request_id}\n{body}", api_secret)
```

The signature binds the HTTP method, path, query string and request id — not
just the body. `X-Request-ID` is reused across retries and is the idempotency
key: a replayed write returns the original response without duplicating the
side effect.

**Pull endpoints:** `health_check`, `pull_branches`, `get_items_for_pos`, `pull_items`, `pull_item_prices`, `pull_customers`, `pull_warehouses`, `pull_stock`, `pull_promotions`, `pull_pos_devices`, `pull_tax_templates`, `pull_discounts`, `pull_employees`, `pull_cashier_shifts`

**Push endpoints:** `sync_sales_invoices`, `sync_daily_sales_summaries`, `sync_cashier_movements`, `update_stock_quantities`, `update_pos_device_status`

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| 401 Authentication | Check API key/secret in Laravel `.env` |
| 403 Permission | Middleware user needs branch User Permissions |
| 422 branch required | Pass `branch` param on branch-scoped endpoints |
| 429 Rate limit | Increase `rate_limit_per_minute` in API Integration Settings |
| HMAC fails | Ensure `ERPNEXT_SIGN_REQUESTS=true`; signature must cover `method\npath\nquery\ntimestamp\nrequest_id\nbody` and a reverse proxy must preserve the request path |
| 401 X-Request-ID required | Send a unique `X-Request-ID` header on every signed request |
| Empty pull results | Seed master data; check branch/warehouse links |
| Scheduler not running | `sudo supervisorctl restart frappe-bench-schedule` |

---

## Deployment checklist

- [ ] Server provisioned (MariaDB, Redis, nginx)
- [ ] Frappe bench + ERPNext installed
- [ ] `custom_erpnext` app installed & migrated
- [ ] `host_name` set to production HTTPS URL
- [ ] Company + Branches + Items + Customers + POS devices created
- [ ] `setup_production_integration` executed
- [ ] Laravel `.env` configured with API credentials
- [ ] Integration tests pass (18/18)
- [ ] Supervisor workers + scheduler running
- [ ] HTTPS enabled
- [ ] Daily backups configured
- [ ] Webhook URL set (optional, for urgent sync)
