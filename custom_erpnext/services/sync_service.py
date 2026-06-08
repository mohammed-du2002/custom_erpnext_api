# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import now_datetime


def trigger_urgent_sync(entity, reference_name):
	"""Queue urgent sync notification for Laravel middleware."""
	frappe.enqueue(
		"custom_erpnext.services.sync_service.notify_middleware",
		queue="short",
		entity=entity,
		reference_name=reference_name,
		job_id=f"urgent-sync-{entity}-{reference_name}",
		deduplicate=True,
	)


def trigger_urgent_sync_for_item(doc, method=None):
	if doc.has_value_changed("standard_rate") or doc.has_value_changed("item_name"):
		trigger_urgent_sync("Item", doc.name)


def trigger_urgent_sync_for_item_price(doc, method=None):
	trigger_urgent_sync("Price", doc.name)


def notify_middleware(entity, reference_name):
	"""Notify Laravel middleware about urgent changes."""
	settings = frappe.get_all(
		"API Integration Settings",
		filters={"system": "Laravel Middleware", "is_active": 1},
		pluck="name",
		limit=1,
	)
	if not settings:
		return

	integration = frappe.get_doc("API Integration Settings", settings[0])
	if not integration.webhook_url:
		return

	frappe.logger("custom_erpnext").info(
		"Urgent sync triggered for %s: %s -> %s", entity, reference_name, integration.webhook_url
	)

	frappe.db.set_value(
		"Sync Configuration",
		{"entity": entity, "sync_type": "Urgent", "is_active": 1},
		"last_sync_time",
		now_datetime(),
		update_modified=False,
	)


def run_scheduled_sync_configs():
	"""Process active sync configurations due for execution."""
	configs = frappe.get_all(
		"Sync Configuration",
		filters={"is_active": 1, "frequency": ["!=", "Manual"]},
		fields=["name", "config_name", "sync_type", "entity", "frequency", "next_sync_time"],
	)

	now = now_datetime()
	for config in configs:
		if config.next_sync_time and config.next_sync_time > now:
			continue

		frappe.enqueue(
			"custom_erpnext.services.sync_service.execute_sync_config",
			queue="long",
			config_name=config.name,
			job_id=f"sync-config-{config.name}",
			deduplicate=True,
		)


def execute_sync_config(config_name):
	config = frappe.get_doc("Sync Configuration", config_name)
	frappe.logger("custom_erpnext").info(
		"Executing sync config: %s (%s / %s)", config.config_name, config.sync_type, config.entity
	)

	config.last_sync_time = now_datetime()
	config.next_sync_time = config.get_next_sync_time()
	config.save(ignore_permissions=True)
