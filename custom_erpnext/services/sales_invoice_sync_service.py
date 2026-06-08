# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now_datetime


BATCH_ENQUEUE_THRESHOLD = 20


def sync_sales_invoices(invoices, request_id=None):
	if not invoices:
		frappe.throw(_("invoices list is required"))

	if len(invoices) > BATCH_ENQUEUE_THRESHOLD:
		frappe.enqueue(
			"custom_erpnext.services.sales_invoice_sync_service.process_invoice_batch",
			queue="long",
			invoices=invoices,
			request_id=request_id,
			timeout=3600,
		)
		return {
			"queued": True,
			"count": len(invoices),
			"message": "Batch queued for processing",
		}

	return process_invoice_batch(invoices, request_id=request_id)


def process_invoice_batch(invoices, request_id=None):
	results = []
	success_count = 0
	failed_count = 0

	for invoice_data in invoices:
		try:
			result = create_or_update_sales_invoice(invoice_data, request_id=request_id)
			results.append(result)
			if result.get("status") == "success":
				success_count += 1
			else:
				failed_count += 1
		except Exception as err:
			frappe.log_error(title="Sales Invoice Sync Failed")
			results.append(
				{
					"offline_invoice_id": invoice_data.get("offline_invoice_id"),
					"status": "failed",
					"error": str(err),
				}
			)
			failed_count += 1

	return {
		"queued": False,
		"total": len(invoices),
		"success_count": success_count,
		"failed_count": failed_count,
		"results": results,
	}


def create_or_update_sales_invoice(data, request_id=None):
	offline_id = data.get("offline_invoice_id")
	if not offline_id:
		frappe.throw(_("offline_invoice_id is required"))

	existing = frappe.db.get_value(
		"Sales Invoice",
		{"offline_invoice_id": offline_id},
		["name", "docstatus", "sync_status"],
		as_dict=True,
	)
	if existing:
		return {
			"offline_invoice_id": offline_id,
			"sales_invoice": existing.name,
			"status": "success",
			"idempotent": True,
			"sync_status": existing.sync_status,
		}

	_validate_invoice_payload(data)
	si = frappe.new_doc("Sales Invoice")
	_map_invoice_header(si, data)
	_map_invoice_items(si, data.get("items") or [])
	_map_invoice_payments(si, data.get("payments") or [])

	from custom_erpnext.services.naming_series_service import apply_branch_naming_series

	apply_branch_naming_series(si)

	si.flags.ignore_permissions = True
	si.insert()

	if cint(data.get("submit", 1)):
		si.submit()

	si.db_set(
		{
			"sync_status": "Synced",
			"sync_log": f"Synced via middleware. request_id={request_id}",
			"offline_invoice_id": offline_id,
		}
	)

	return {
		"offline_invoice_id": offline_id,
		"sales_invoice": si.name,
		"status": "success",
		"idempotent": False,
		"sync_status": "Synced",
	}


def _validate_invoice_payload(data):
	required = ["company", "customer", "items"]
	for field in required:
		if not data.get(field):
			frappe.throw(_("{0} is required").format(field))

	if not data.get("items"):
		frappe.throw(_("At least one item is required"))

	if data.get("branch"):
		from custom_erpnext.api.validators import validate_branch_access

		validate_branch_access(data["branch"])


def _map_invoice_header(si, data):
	si.update(
		{
			"company": data["company"],
			"customer": data["customer"],
			"posting_date": data.get("posting_date") or getdate(),
			"due_date": data.get("due_date"),
			"is_pos": cint(data.get("is_pos", 1)),
			"is_return": cint(data.get("is_return", 0)),
			"return_against": data.get("return_against"),
			"branch": data.get("branch"),
			"cost_center": data.get("cost_center"),
			"pos_device": data.get("pos_device"),
			"cashier": data.get("cashier"),
			"shift_id": data.get("shift_id"),
			"pos_profile": data.get("pos_profile"),
			"offline_invoice_id": data.get("offline_invoice_id"),
			"sync_status": "Pending",
			"set_warehouse": data.get("warehouse"),
			"selling_price_list": data.get("price_list"),
			"additional_discount_percentage": flt(data.get("discount_percent")),
			"coupon_code": data.get("coupon_code"),
			"promotion_applied": data.get("promotion_applied"),
			"tabby_reference": data.get("tabby_reference"),
			"tamara_reference": data.get("tamara_reference"),
			"wallet_amount": flt(data.get("wallet_amount")),
			"loyalty_points": cint(data.get("loyalty_points_used")),
			"loyalty_amount": flt(data.get("loyalty_points_value")),
			"remarks": data.get("remarks"),
		}
	)

	if data.get("taxes_and_charges"):
		si.taxes_and_charges = data["taxes_and_charges"]


def _map_invoice_items(si, items):
	for item in items:
		si.append(
			"items",
			{
				"item_code": item["item_code"],
				"qty": flt(item.get("qty")),
				"rate": flt(item.get("rate")),
				"discount_percentage": flt(item.get("discount_percentage")),
				"warehouse": item.get("warehouse") or si.set_warehouse,
				"uom": item.get("uom"),
				"description": item.get("description"),
			},
		)


def _map_invoice_payments(si, payments):
	for payment in payments:
		si.append(
			"payments",
			{
				"mode_of_payment": payment["mode_of_payment"],
				"amount": flt(payment.get("amount")),
				"reference_no": payment.get("reference_no"),
				"payment_provider": payment.get("payment_provider"),
				"transaction_id": payment.get("transaction_id"),
			},
		)


def sync_daily_sales_summaries(summaries):
	if not summaries:
		frappe.throw(_("summaries list is required"))

	results = []
	for summary in summaries:
		results.append(_upsert_daily_sales_summary(summary))

	return {"total": len(summaries), "results": results}


def _upsert_daily_sales_summary(data):
	if data.get("branch"):
		from custom_erpnext.api.validators import validate_branch_access

		validate_branch_access(data["branch"])

	offline_key = f"{data.get('summary_date')}-{data.get('pos_device')}-{data.get('branch')}"
	existing = frappe.db.exists(
		"Daily Sales Summary",
		{
			"summary_date": data.get("summary_date"),
			"pos_device": data.get("pos_device"),
			"branch": data.get("branch"),
		},
	)

	if existing:
		doc = frappe.get_doc("Daily Sales Summary", existing)
		doc.update(_summary_fields(data))
		doc.status = "Synced"
		doc.synced_to_erp = 1
		doc.sync_time = now_datetime()
		doc.save(ignore_permissions=True)
		return {"name": doc.name, "status": "updated", "offline_key": offline_key}

	doc = frappe.new_doc("Daily Sales Summary")
	doc.update(_summary_fields(data))
	from custom_erpnext.services.naming_series_service import apply_branch_naming_series

	apply_branch_naming_series(doc)
	doc.naming_series = doc.naming_series or "DSS-.YYYY.-.#####"
	doc.status = "Synced"
	doc.synced_to_erp = 1
	doc.sync_time = now_datetime()
	doc.insert(ignore_permissions=True)
	return {"name": doc.name, "status": "created", "offline_key": offline_key}


def _summary_fields(data):
	return {
		"summary_date": data.get("summary_date"),
		"branch": data.get("branch"),
		"pos_device": data.get("pos_device"),
		"cashier": data.get("cashier"),
		"opening_cash": flt(data.get("opening_cash")),
		"total_sales": flt(data.get("total_sales")),
		"total_returns": flt(data.get("total_returns")),
		"net_sales": flt(data.get("net_sales")),
		"cash_sales": flt(data.get("cash_sales")),
		"card_sales": flt(data.get("card_sales")),
		"other_sales": flt(data.get("other_sales")),
		"total_discounts": flt(data.get("total_discounts")),
		"total_tax": flt(data.get("total_tax")),
		"transaction_count": cint(data.get("transaction_count")),
		"closing_cash": flt(data.get("closing_cash")),
	}


def update_stock_quantities(stock_updates, warehouse=None):
	if not stock_updates:
		frappe.throw(_("stock_updates list is required"))
	if not warehouse:
		frappe.throw(_("warehouse is required"))

	results = []
	for row in stock_updates:
		item_code = row.get("item_code")
		qty = flt(row.get("qty"))
		if not item_code:
			continue

		actual_qty = frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty") or 0
		results.append(
			{
				"item_code": item_code,
				"warehouse": warehouse,
				"erp_qty": actual_qty,
				"pos_qty": qty,
				"variance": flt(qty) - flt(actual_qty),
			}
		)

	return {"warehouse": warehouse, "count": len(results), "items": results}
