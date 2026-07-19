# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe


def execute():
	"""Ensure the webhook credential fields exist and seed them from site config/env.

	The DocType JSON already declares ``webhook_api_key`` / ``webhook_secret``; this
	patch reloads it and optionally backfills values from site config so an admin does
	not have to re-enter them after deploy. Values already set are never overwritten.
	"""
	frappe.reload_doc("custom_erpnext", "doctype", "api_integration_settings")

	from custom_erpnext.setup.laravel_integration import INTEGRATION_NAME

	if not frappe.db.exists("API Integration Settings", INTEGRATION_NAME):
		return

	doc = frappe.get_doc("API Integration Settings", INTEGRATION_NAME)
	changed = False

	if not doc.get_password("webhook_api_key", raise_exception=False):
		seeded_key = frappe.conf.get("erpnext_webhook_api_key")
		if seeded_key:
			doc.webhook_api_key = seeded_key
			changed = True

	if not doc.get_password("webhook_secret", raise_exception=False):
		seeded_secret = frappe.conf.get("erpnext_webhook_secret")
		if seeded_secret:
			doc.webhook_secret = seeded_secret
			changed = True

	if changed:
		doc.save(ignore_permissions=True)
		frappe.db.commit()
