# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Bootstrap ERPNext side of Laravel Middleware integration."""

import frappe

INTEGRATION_USER = "middleware@laravel.local"
INTEGRATION_NAME = "Laravel Middleware"

DEFAULT_SYNC_CONFIGS = [
	{
		"config_name": "Pull Items",
		"sync_type": "Pull (ERP→POS)",
		"entity": "Item",
		"frequency": "Every 10 Minutes",
		"batch_size": 100,
		"timeout_seconds": 60,
		"retry_attempts": 3,
	},
	{
		"config_name": "Pull Item Prices",
		"sync_type": "Pull (ERP→POS)",
		"entity": "Price",
		"frequency": "Every 10 Minutes",
		"batch_size": 200,
		"timeout_seconds": 60,
		"retry_attempts": 3,
	},
	{
		"config_name": "Pull Customers",
		"sync_type": "Pull (ERP→POS)",
		"entity": "Customer",
		"frequency": "Hourly",
		"batch_size": 100,
		"timeout_seconds": 60,
		"retry_attempts": 3,
	},
	{
		"config_name": "Pull Warehouses",
		"sync_type": "Pull (ERP→POS)",
		"entity": "Warehouse",
		"frequency": "Daily",
		"batch_size": 50,
		"timeout_seconds": 60,
		"retry_attempts": 3,
	},
	{
		"config_name": "Pull Stock",
		"sync_type": "Pull (ERP→POS)",
		"entity": "Stock",
		"frequency": "Every 10 Minutes",
		"batch_size": 200,
		"timeout_seconds": 90,
		"retry_attempts": 3,
	},
	{
		"config_name": "Pull Promotions",
		"sync_type": "Pull (ERP→POS)",
		"entity": "Promotion",
		"frequency": "Hourly",
		"batch_size": 50,
		"timeout_seconds": 60,
		"retry_attempts": 3,
	},
	{
		"config_name": "Pull Tax Templates",
		"sync_type": "Pull (ERP→POS)",
		"entity": "Tax",
		"frequency": "Daily",
		"batch_size": 50,
		"timeout_seconds": 60,
		"retry_attempts": 3,
	},
	{
		"config_name": "Push Sales Invoices",
		"sync_type": "Push (POS→ERP)",
		"entity": "All",
		"frequency": "Manual",
		"batch_size": 20,
		"timeout_seconds": 120,
		"retry_attempts": 5,
	},
	{
		"config_name": "Push Daily Summaries",
		"sync_type": "Push (POS→ERP)",
		"entity": "All",
		"frequency": "Manual",
		"batch_size": 10,
		"timeout_seconds": 60,
		"retry_attempts": 3,
	},
	{
		"config_name": "Urgent Item Changes",
		"sync_type": "Urgent",
		"entity": "Item",
		"frequency": "Real-time",
		"batch_size": 1,
		"timeout_seconds": 30,
		"retry_attempts": 3,
	},
	{
		"config_name": "Urgent Price Changes",
		"sync_type": "Urgent",
		"entity": "Price",
		"frequency": "Real-time",
		"batch_size": 1,
		"timeout_seconds": 30,
		"retry_attempts": 3,
	},
]


def setup_production_integration(
	site_url=None,
	webhook_url=None,
	laravel_api_endpoint=None,
	rate_limit_per_minute=120,
):
	"""Full production bootstrap: user, API settings, sync configs."""
	integration = setup_laravel_integration(
		site_url=site_url,
		webhook_url=webhook_url,
		rate_limit_per_minute=rate_limit_per_minute,
	)
	sync_configs = setup_sync_configurations(laravel_api_endpoint=laravel_api_endpoint)
	frappe.db.commit()

	return {
		**integration,
		"sync_configurations": sync_configs,
		"next_steps": [
			"Copy env snippet into Laravel .env",
			"Run: bench --site SITE execute custom_erpnext.setup.integration_tests.run_laravel_integration_tests",
			"Ensure supervisor workers + scheduler are running",
		],
	}


def setup_laravel_integration(
	site_url=None,
	webhook_url=None,
	rate_limit_per_minute=120,
):
	"""Create middleware API user, keys, and integration settings."""
	site_url = site_url or _guess_site_url()
	user = _ensure_integration_user()
	keys = _generate_api_keys(user)

	settings = _ensure_integration_settings(
		site_url=site_url,
		webhook_url=webhook_url,
		rate_limit_per_minute=rate_limit_per_minute,
		api_key=keys["api_key"],
		api_secret=keys["api_secret"],
	)

	fix_middleware_user_roles()
	_sync_user_branch_access(user)

	return {
		"site_url": site_url,
		"integration_user": user,
		"api_key": keys["api_key"],
		"api_secret": keys["api_secret"],
		"integration_settings": settings,
		"webhook_url": webhook_url or "",
		"env": _build_env_snippet(site_url, keys["api_key"], keys["api_secret"], webhook_url),
	}


def setup_sync_configurations(laravel_api_endpoint=None):
	"""Create default Sync Configuration records for Laravel orchestration."""
	created = []
	for row in DEFAULT_SYNC_CONFIGS:
		name = row["config_name"]
		values = {**row, "is_active": 1}
		if laravel_api_endpoint:
			values["api_endpoint"] = laravel_api_endpoint

		if frappe.db.exists("Sync Configuration", name):
			doc = frappe.get_doc("Sync Configuration", name)
			doc.update(values)
			doc.save(ignore_permissions=True)
		else:
			doc = frappe.get_doc({"doctype": "Sync Configuration", **values})
			doc.insert(ignore_permissions=True)

		created.append(name)

	return created


def _guess_site_url():
	site = frappe.local.site
	host = frappe.conf.get("host_name")
	if host:
		return host if host.startswith("http") else f"https://{host}"
	return f"https://{site}"


def _ensure_integration_user():
	if frappe.db.exists("User", INTEGRATION_USER):
		return INTEGRATION_USER

	doc = frappe.get_doc(
		{
			"doctype": "User",
			"email": INTEGRATION_USER,
			"first_name": "Laravel",
			"last_name": "Middleware",
			"send_welcome_email": 0,
			"enabled": 1,
		}
	)
	for role in ("Sales User", "Stock User", "Accounts User", "Purchase User"):
		doc.append("roles", {"role": role})
	doc.insert(ignore_permissions=True)
	doc.new_password = frappe.generate_hash(length=24)
	doc.save(ignore_permissions=True)
	return doc.name


def _generate_api_keys(user):
	doc = frappe.get_doc("User", user)
	api_secret = frappe.generate_hash(length=15)
	if not doc.api_key:
		doc.api_key = frappe.generate_hash(length=15)
	doc.api_secret = api_secret
	doc.save(ignore_permissions=True)
	return {"api_key": doc.api_key, "api_secret": api_secret}


def fix_middleware_user_roles():
	"""Remove System Manager from middleware user so HMAC auth is enforced."""
	if not frappe.db.exists("User", INTEGRATION_USER):
		return

	doc = frappe.get_doc("User", INTEGRATION_USER)
	doc.roles = [row for row in doc.roles if row.role != "System Manager"]
	existing = {row.role for row in doc.roles}
	for role in ("Sales User", "Stock User", "Accounts User", "Purchase User"):
		if role not in existing:
			doc.append("roles", {"role": role})
	doc.save(ignore_permissions=True)


def _sync_user_branch_access(user):
	from custom_erpnext.services.branch_permission_service import sync_user_branch_permissions

	branches = frappe.get_all("Company Branch", filters={"is_active": 1}, pluck="name")
	if not branches:
		return

	rows = [{"branch": branch, "is_default": 1 if idx == 0 else 0} for idx, branch in enumerate(branches)]
	sync_user_branch_permissions(user, branch_rows=rows)


def _ensure_integration_settings(site_url, webhook_url, rate_limit_per_minute, api_key=None, api_secret=None):
	name = INTEGRATION_NAME
	values = {
		"system": "Laravel Middleware",
		"is_active": 1,
		"auth_type": "API Key",
		"endpoint_url": site_url,
		"webhook_url": webhook_url or "",
		"rate_limit_per_minute": rate_limit_per_minute,
		"request_timeout": 30,
	}

	if frappe.db.exists("API Integration Settings", name):
		doc = frappe.get_doc("API Integration Settings", name)
		doc.update(values)
	else:
		doc = frappe.get_doc({"doctype": "API Integration Settings", "integration_name": name, **values})

	if api_key:
		doc.api_key = api_key
	if api_secret:
		doc.api_secret = api_secret

	doc.save(ignore_permissions=True)
	return doc.name


def _build_env_snippet(site_url, api_key, api_secret, webhook_url=None):
	lines = [
		"ERPNEXT_BASE_URL=" + site_url,
		"ERPNEXT_API_KEY=" + api_key,
		"ERPNEXT_API_SECRET=" + api_secret,
		"ERPNEXT_SIGN_REQUESTS=true",
		"ERPNEXT_TIMEOUT=30",
		"ERPNEXT_RETRY_TIMES=3",
		"ERPNEXT_RETRY_SLEEP_MS=500",
	]
	if webhook_url:
		lines.append("ERPNEXT_WEBHOOK_URL=" + webhook_url)
	return "\n".join(lines)
