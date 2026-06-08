# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe

from custom_erpnext.api.auth import middleware_api
from custom_erpnext.api.response import success
from custom_erpnext.api.validators import parse_json_field, validate_branch_access
from custom_erpnext.services import sales_invoice_sync_service as si_sync


@frappe.whitelist(allow_guest=True, methods=["POST"])
@middleware_api
def sync_sales_invoices(invoices=None, request_id=None):
	invoices = parse_json_field(invoices, "invoices")
	if isinstance(invoices, dict):
		invoices = [invoices]

	request_id = request_id or getattr(frappe.local, "middleware_request_id", None)
	result = si_sync.sync_sales_invoices(invoices=invoices, request_id=request_id)
	return success(result, meta={"request_id": request_id})


@frappe.whitelist(allow_guest=True, methods=["POST"])
@middleware_api
def sync_daily_sales_summaries(summaries=None, request_id=None):
	summaries = parse_json_field(summaries, "summaries")
	if isinstance(summaries, dict):
		summaries = [summaries]

	result = si_sync.sync_daily_sales_summaries(summaries)
	return success(result, meta={"request_id": request_id})


@frappe.whitelist(allow_guest=True, methods=["POST"])
@middleware_api
def update_stock_quantities(stock_updates=None, warehouse=None, branch=None, request_id=None):
	if branch and not warehouse:
		validate_branch_access(branch)
		warehouse = frappe.db.get_value("Company Branch", branch, "warehouse")

	stock_updates = parse_json_field(stock_updates, "stock_updates")
	result = si_sync.update_stock_quantities(stock_updates, warehouse=warehouse)
	return success(result, meta={"request_id": request_id, "branch": branch})


@frappe.whitelist(allow_guest=True, methods=["POST"])
@middleware_api
def update_pos_device_status(device_id=None, is_online=None, last_sync_time=None):
	if not device_id:
		frappe.throw("device_id is required")

	if not frappe.db.exists("POS Device", {"device_id": device_id}):
		frappe.throw(f"POS Device {device_id} not found")

	updates = {}
	if is_online is not None:
		updates["is_online"] = int(is_online)
	if last_sync_time:
		updates["last_sync_time"] = last_sync_time

	if updates:
		frappe.db.set_value("POS Device", {"device_id": device_id}, updates, update_modified=True)

	return success({"device_id": device_id, "updated": updates})
