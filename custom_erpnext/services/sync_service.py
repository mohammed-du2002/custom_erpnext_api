# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import hashlib
import hmac
import json
import time
import uuid

import frappe
from frappe.integrations.utils import make_post_request
from frappe.utils import now_datetime

INTEGRATION_SYSTEM = "Laravel Middleware"
WEBHOOK_MAX_ATTEMPTS = 3
WEBHOOK_RETRY_DELAY_SECONDS = 30


def trigger_urgent_sync(entity, reference_name, config_name=None):
	"""Queue urgent sync notification for Laravel middleware."""
	if frappe.flags.in_import or frappe.flags.in_patch:
		return

	frappe.enqueue(
		"custom_erpnext.services.sync_service.notify_middleware",
		queue="short",
		entity=entity,
		reference_name=reference_name,
		config_name=config_name,
		attempt=1,
		job_id=f"urgent-sync-{entity}-{reference_name}",
		deduplicate=True,
	)


def trigger_urgent_sync_for_item(doc, method=None):
	trigger_urgent_sync("Item", doc.name, config_name="Urgent Item Changes")


def trigger_urgent_sync_for_item_price(doc, method=None):
	trigger_urgent_sync("Price", doc.name, config_name="Urgent Price Changes")


def trigger_urgent_sync_for_customer(doc, method=None):
	trigger_urgent_sync("Customer", doc.name, config_name="Urgent Customer Changes")


def trigger_urgent_sync_for_promotion(doc, method=None):
	trigger_urgent_sync("Promotion", doc.name, config_name="Urgent Promotion Changes")


def trigger_urgent_sync_for_discount(doc, method=None):
	trigger_urgent_sync("Discount", doc.name, config_name="Urgent Discount Changes")


def notify_middleware(entity, reference_name, config_name=None, attempt=1):
	"""Notify Laravel middleware about urgent changes."""
	integration = _get_active_integration()
	if not integration or not integration.webhook_url:
		return

	_touch_urgent_sync_config(entity=entity, config_name=config_name)

	payload = {
		"event": "urgent_sync",
		"entity": entity,
		"reference_name": reference_name,
		"site": frappe.local.site,
		"timestamp": now_datetime().isoformat(),
	}
	request_id = str(uuid.uuid4())

	frappe.logger("custom_erpnext").info(
		"Urgent sync triggered for %s: %s -> %s (attempt %s)",
		entity,
		reference_name,
		integration.webhook_url,
		attempt,
	)

	try:
		status_code = _post_webhook(integration, payload, request_id=request_id)
		frappe.db.set_value(
			"API Integration Settings",
			integration.name,
			{
				"last_response_status": status_code,
				"last_response_time": now_datetime(),
			},
			update_modified=False,
		)
	except Exception as err:
		frappe.logger("custom_erpnext").warning(
			"Urgent sync webhook failed for %s (%s): %s", entity, reference_name, err
		)
		if attempt < WEBHOOK_MAX_ATTEMPTS:
			frappe.enqueue(
				"custom_erpnext.services.sync_service.notify_middleware",
				queue="short",
				entity=entity,
				reference_name=reference_name,
				config_name=config_name,
				attempt=attempt + 1,
				job_id=f"urgent-sync-retry-{entity}-{reference_name}-{attempt + 1}",
				enqueue_after=WEBHOOK_RETRY_DELAY_SECONDS,
			)
		else:
			frappe.log_error(
				title=f"Urgent sync webhook failed: {entity} {reference_name}",
				message=str(err),
			)


def _get_active_integration():
	rows = frappe.get_all(
		"API Integration Settings",
		filters={"system": INTEGRATION_SYSTEM, "is_active": 1},
		pluck="name",
		limit=1,
	)
	if not rows:
		return None
	return frappe.get_doc("API Integration Settings", rows[0])


def _post_webhook(integration, payload, request_id=None):
	body = json.dumps(payload, separators=(",", ":"), default=str)
	timestamp = str(int(time.time()))
	headers = {
		"Content-Type": "application/json",
		"X-Request-ID": request_id or str(uuid.uuid4()),
		"X-Timestamp": timestamp,
	}

	api_secret = integration.get_password("api_secret")
	if api_secret:
		message = f"{timestamp}.{body}"
		headers["X-Signature"] = hmac.new(
			api_secret.encode("utf-8"),
			message.encode("utf-8"),
			hashlib.sha256,
		).hexdigest()

	api_key = integration.get_password("api_key")
	if api_key and api_secret:
		headers["Authorization"] = f"token {api_key}:{api_secret}"

	timeout = integration.request_timeout or 30
	make_post_request(
		integration.webhook_url,
		data=body,
		headers=headers,
		timeout=timeout,
	)
	integration_request = getattr(frappe.flags, "integration_request", None)
	if integration_request is not None:
		return integration_request.status_code
	return 200


def _touch_urgent_sync_config(entity=None, config_name=None):
	filters = {"sync_type": "Urgent", "is_active": 1}
	if config_name:
		filters["config_name"] = config_name
	elif entity:
		filters["entity"] = entity
	else:
		return

	frappe.db.set_value(
		"Sync Configuration",
		filters,
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
