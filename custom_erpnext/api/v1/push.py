# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from custom_erpnext.api.auth import idempotent_write, middleware_api
from custom_erpnext.api.response import success
from custom_erpnext.api.validators import (
	parse_json_field,
	validate_branch_access,
	validate_branch_warehouse_consistency,
	validate_warehouse_access,
)
from custom_erpnext.services import cashier_movement_sync_service as cm_sync
from custom_erpnext.services import sales_invoice_sync_service as si_sync


@frappe.whitelist(allow_guest=True, methods=["POST"])
@middleware_api
@idempotent_write
def sync_sales_invoices(invoices=None, request_id=None):
	invoices = parse_json_field(invoices, "invoices")
	if isinstance(invoices, dict):
		invoices = [invoices]

	request_id = request_id or getattr(frappe.local, "middleware_request_id", None)
	result = si_sync.sync_sales_invoices(invoices=invoices, request_id=request_id)
	return success(result, meta={"request_id": request_id})


@frappe.whitelist(allow_guest=True, methods=["POST"])
@middleware_api
@idempotent_write
def sync_daily_sales_summaries(summaries=None, request_id=None):
	summaries = parse_json_field(summaries, "summaries")
	if isinstance(summaries, dict):
		summaries = [summaries]

	result = si_sync.sync_daily_sales_summaries(summaries)
	return success(result, meta={"request_id": request_id})


@frappe.whitelist(allow_guest=True, methods=["POST"])
@middleware_api
@idempotent_write
def update_stock_quantities(
	stock_updates=None, warehouse=None, branch=None, apply=0, request_id=None
):
	stock_updates = parse_json_field(stock_updates, "stock_updates")

	if branch and not warehouse:
		validate_branch_access(branch)
		warehouse = frappe.db.get_value("Company Branch", branch, "warehouse")

	if not warehouse:
		frappe.throw(_("warehouse or branch is required"))

	validate_branch_warehouse_consistency(branch, warehouse)
	warehouse_branch = validate_warehouse_access(warehouse, require_branch=True)
	branch = branch or warehouse_branch
	validate_branch_access(branch)

	result = si_sync.reconcile_stock_quantities(stock_updates, warehouse=warehouse, apply=apply)
	return success(result, meta={"request_id": request_id, "branch": branch})


@frappe.whitelist(allow_guest=True, methods=["POST"])
@middleware_api
@idempotent_write
def sync_cashier_movements(movements=None, request_id=None):
	movements = parse_json_field(movements, "movements")
	if isinstance(movements, dict):
		movements = [movements]

	request_id = request_id or getattr(frappe.local, "middleware_request_id", None)
	result = cm_sync.sync_cashier_movements(movements=movements, request_id=request_id)
	return success(result, meta={"request_id": request_id})


@frappe.whitelist(allow_guest=True, methods=["POST"])
@middleware_api
@idempotent_write
def update_pos_device_status(device_id=None, is_online=None, last_sync_time=None):
	if not device_id:
		frappe.throw("device_id is required")

	device_branch = frappe.db.get_value("POS Device", {"device_id": device_id}, "branch")
	if not device_branch:
		frappe.throw(_("POS Device {0} not found").format(device_id))

	validate_branch_access(device_branch)

	updates = {}
	if is_online is not None:
		updates["is_online"] = int(is_online)
	if last_sync_time:
		updates["last_sync_time"] = last_sync_time

	if updates:
		frappe.db.set_value("POS Device", {"device_id": device_id}, updates, update_modified=True)

	return success({"device_id": device_id, "updated": updates})


# ZATCA status is a read operation exposed via
# custom_erpnext.api.v1.pull.get_sales_invoice_zatca_status (and
# custom_erpnext.api.client.get_sales_invoice_zatca_status for desk). It is
# intentionally not duplicated here on the push surface.
