# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import hashlib
import hmac
import json
import uuid

import frappe
from frappe.utils import get_request_session, now_datetime

INTEGRATION_SYSTEM = "Laravel Middleware"
WEBHOOK_MAX_ATTEMPTS = 3
WEBHOOK_RETRY_DELAY_SECONDS = 30

# Map Frappe DocType -> Laravel middleware webhook entity + urgent Sync Configuration.
# The `entity` value MUST match Laravel's PullSyncEntityEnum (lowercase, plural).
ENTITY_CONFIG = {
	"Item": {"entity": "items", "config_name": "Urgent Item Changes"},
	"Item Price": {"entity": "item_prices", "config_name": "Urgent Price Changes"},
	"Customer": {"entity": "customers", "config_name": "Urgent Customer Changes"},
	"Promotion Rule": {"entity": "promotions", "config_name": "Urgent Promotion Changes"},
	"User Discount Profile": {"entity": "discounts", "config_name": "Urgent Discount Changes"},
}

# Map the Frappe doc event to the Laravel webhook operation.
OPERATION_BY_METHOD = {
	"after_insert": "create",
	"on_update": "update",
	"on_trash": "delete",
}


def trigger_urgent_sync_doc_event(doc, method=None):
	"""Generic doc-event handler wired to after_insert / on_update / on_trash.

	Resolves the Laravel entity + operation from the DocType and event, then
	queues a targeted webhook. Skips the redundant ``on_update`` that Frappe
	fires during ``insert`` so a new record emits a single ``create`` event.
	"""
	mapping = ENTITY_CONFIG.get(doc.doctype)
	if not mapping:
		return

	operation = OPERATION_BY_METHOD.get(method)
	if not operation:
		return

	if operation == "update" and getattr(doc.flags, "in_insert", False):
		return

	branch_id, company_id = _extract_scope(doc)
	trigger_urgent_sync(
		entity=mapping["entity"],
		erp_id=doc.name,
		operation=operation,
		config_name=mapping["config_name"],
		branch_id=branch_id,
		company_id=company_id,
	)


def trigger_urgent_sync(
	entity, erp_id, operation="update", config_name=None, branch_id=None, company_id=None
):
	"""Queue an urgent sync notification for the Laravel middleware."""
	if frappe.flags.in_import or frappe.flags.in_patch or frappe.flags.in_install:
		return

	frappe.enqueue(
		"custom_erpnext.services.sync_service.notify_middleware",
		queue="short",
		entity=entity,
		erp_id=erp_id,
		operation=operation,
		config_name=config_name,
		branch_id=branch_id,
		company_id=company_id,
		attempt=1,
		job_id=f"urgent-sync-{entity}-{erp_id}-{operation}",
		deduplicate=True,
	)


def _extract_scope(doc):
	"""Best-effort extraction of branch/company scope for the webhook payload."""
	company_id = doc.get("company") if hasattr(doc, "get") else None

	branch_id = None
	for fieldname in ("branch", "company_branch", "custom_branch", "erpnext_branch"):
		value = doc.get(fieldname) if hasattr(doc, "get") else None
		if value:
			branch_id = value
			break

	return branch_id, company_id


def notify_middleware(
	entity,
	erp_id,
	operation="update",
	config_name=None,
	branch_id=None,
	company_id=None,
	attempt=1,
):
	"""Notify the Laravel middleware about an urgent change."""
	integration = _get_active_integration()
	if not integration or not integration.webhook_url:
		return

	_touch_urgent_sync_config(entity=entity, config_name=config_name)

	payload = {
		"entity": entity,
		"erp_id": erp_id,
		"operation": operation,
		"branch_id": branch_id or "",
		"company_id": company_id or "",
	}
	request_id = str(uuid.uuid4())

	frappe.logger("custom_erpnext").info(
		"Urgent sync triggered for %s/%s (%s) -> %s (attempt %s)",
		entity,
		erp_id,
		operation,
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
			"Urgent sync webhook failed for %s/%s (%s): %s", entity, erp_id, operation, err
		)
		if attempt < WEBHOOK_MAX_ATTEMPTS:
			frappe.enqueue(
				"custom_erpnext.services.sync_service.notify_middleware",
				queue="short",
				entity=entity,
				erp_id=erp_id,
				operation=operation,
				config_name=config_name,
				branch_id=branch_id,
				company_id=company_id,
				attempt=attempt + 1,
				job_id=f"urgent-sync-retry-{entity}-{erp_id}-{operation}-{attempt + 1}",
				enqueue_after=WEBHOOK_RETRY_DELAY_SECONDS,
			)
		else:
			frappe.log_error(
				title=f"Urgent sync webhook failed: {entity} {erp_id} ({operation})",
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
	headers = {
		"Content-Type": "application/json",
		"X-Request-ID": request_id or str(uuid.uuid4()),
	}

	webhook_api_key = _get_secret(integration, "webhook_api_key")
	if webhook_api_key:
		headers["X-Webhook-API-Key"] = webhook_api_key

	# Laravel verifies hash_hmac('sha256', <raw request body>, secret); sign the exact
	# body bytes we send, with no timestamp prefix, only when a secret is configured.
	webhook_secret = _get_secret(integration, "webhook_secret")
	if webhook_secret:
		headers["X-Webhook-Signature"] = hmac.new(
			webhook_secret.encode("utf-8"),
			body.encode("utf-8"),
			hashlib.sha256,
		).hexdigest()

	timeout = integration.request_timeout or 30
	session = get_request_session()
	response = session.post(
		integration.webhook_url,
		data=body,
		headers=headers,
		timeout=timeout,
	)
	frappe.flags.integration_request = response
	response.raise_for_status()
	return response.status_code


def _get_secret(integration, fieldname):
	"""Read an (optional) password field without raising when it is unset."""
	try:
		return integration.get_password(fieldname, raise_exception=False)
	except TypeError:
		return integration.get_password(fieldname)


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
