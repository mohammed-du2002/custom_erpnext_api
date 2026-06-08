# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Bootstrap ERPNext side of Laravel Middleware integration."""

import frappe

INTEGRATION_USER = "middleware@laravel.local"
INTEGRATION_NAME = "Laravel Middleware"


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
	frappe.db.commit()

	return {
		"site_url": site_url,
		"integration_user": user,
		"api_key": keys["api_key"],
		"api_secret": keys["api_secret"],
		"integration_settings": settings,
		"env": _build_env_snippet(site_url, keys["api_key"], keys["api_secret"], webhook_url),
	}


def _guess_site_url():
	site = frappe.local.site
	host = frappe.conf.get("host_name")
	if host:
		return host if host.startswith("http") else f"http://{host}"
	return f"http://{site}"


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
	doc.new_password = frappe.generate_hash(length=12)
	doc.save(ignore_permissions=True)

	_sync_user_branch_access(doc.name)
	return doc.name


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


def _build_env_snippet(site_url, api_key, api_secret, webhook_url=None):
	doc = frappe.get_doc("User", user)
	api_secret = frappe.generate_hash(length=15)
	if not doc.api_key:
		doc.api_key = frappe.generate_hash(length=15)
	doc.api_secret = api_secret
	doc.save(ignore_permissions=True)
	return {"api_key": doc.api_key, "api_secret": api_secret}


def _sync_user_branch_access(user):
	"""Grant middleware user access to all active branches."""
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
	frappe.db.commit()
	lines = [
		"ERPNEXT_BASE_URL=" + site_url,
		"ERPNEXT_API_KEY=" + api_key,
		"ERPNEXT_API_SECRET=" + api_secret,
		"ERPNEXT_SIGN_REQUESTS=true",
		"ERPNEXT_TIMEOUT=30",
	]
	if webhook_url:
		lines.append("ERPNEXT_WEBHOOK_URL=" + webhook_url)
	return "\n".join(lines)
