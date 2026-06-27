# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now_datetime


BATCH_ENQUEUE_THRESHOLD = 20


@contextmanager
def middleware_sync_context():
	"""Bypass branch link checks while Laravel middleware creates POS invoices."""
	previous = getattr(frappe.local, "middleware_sync", False)
	frappe.local.middleware_sync = True
	try:
		yield
	finally:
		frappe.local.middleware_sync = previous


def sync_sales_invoices(invoices, request_id=None):
	if not invoices:
		frappe.throw(_("invoices list is required"))

	if len(invoices) > BATCH_ENQUEUE_THRESHOLD:
		job = frappe.enqueue(
			"custom_erpnext.services.sales_invoice_sync_service.process_invoice_batch",
			queue="long",
			invoices=invoices,
			request_id=request_id,
			timeout=3600,
		)
		return {
			"queued": True,
			"count": len(invoices),
			"job_id": getattr(job, "id", None),
			"message": "Batch queued for processing",
		}

	return process_invoice_batch(invoices, request_id=request_id)


def process_invoice_batch(invoices, request_id=None):
	results = []
	success_count = 0
	failed_count = 0

	with middleware_sync_context():
		for invoice_data in invoices:
			try:
				result = create_or_update_sales_invoice(invoice_data, request_id=request_id)
				results.append(result)
				if result.get("status") == "success":
					success_count += 1
				else:
					failed_count += 1
			except Exception as err:
				frappe.log_error(
					title="Sales Invoice Sync Failed",
					message=(
						f"offline_invoice_id={invoice_data.get('offline_invoice_id')} "
						f"request_id={request_id}\n\n{frappe.get_traceback()}"
					),
				)
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


def find_invoice_by_sync_key(sync_key):
	"""Resolve a Sales Invoice by offline or online middleware idempotency key."""
	sync_key = (sync_key or "").strip()
	if not sync_key:
		return None

	for field in ("offline_invoice_id", "online_invoice_id"):
		name = frappe.db.get_value("Sales Invoice", {field: sync_key}, "name")
		if name:
			return name

	return None


def _extract_sync_key(data):
	return (data.get("offline_invoice_id") or data.get("online_invoice_id") or "").strip()


def _resolve_sync_storage(data):
	"""Map API payload to the Sales Invoice idempotency field (SRS §7.3).

	B2C/offline queue uses ``offline_invoice_id``. B2B issued while online uses
	``online_invoice_id`` so ``validate_b2b_requires_online`` is not triggered.
	"""
	issued_online = cint(data.get("issued_online"))
	sync_key = _extract_sync_key(data)

	if issued_online:
		if not sync_key:
			frappe.throw(
				_("online_invoice_id or offline_invoice_id is required when issued_online=1")
			)
		return sync_key, "online_invoice_id"

	if not sync_key:
		frappe.throw(_("offline_invoice_id is required"))

	return sync_key, "offline_invoice_id"


def create_or_update_sales_invoice(data, request_id=None):
	sync_key = _extract_sync_key(data)
	if not sync_key:
		frappe.throw(_("offline_invoice_id is required"))

	existing_name = find_invoice_by_sync_key(sync_key)
	existing = (
		frappe.db.get_value(
			"Sales Invoice",
			existing_name,
			["name", "docstatus", "sync_status"],
			as_dict=True,
		)
		if existing_name
		else None
	)

	if existing:
		# Submitted -> truly idempotent, nothing to do.
		if existing.docstatus == 1:
			return _invoice_result(sync_key, existing.name, idempotent=True, sync_status=existing.sync_status or "Synced")

		# Cancelled -> do not recreate; report state back to the caller.
		if existing.docstatus == 2:
			return _invoice_result(
				sync_key, existing.name, idempotent=True, status="cancelled", sync_status="Failed"
			)

		# Draft left behind by a failed submit -> re-apply full payload when sent,
		# then retry finalisation instead of returning a fake success.
		si = frappe.get_doc("Sales Invoice", existing.name)
		if _has_full_invoice_payload(data):
			_validate_invoice_payload(data)
			_apply_invoice_payload(si, data)
			si.flags.ignore_permissions = True
			si.save()
		return _finalize_invoice(si, data, sync_key, request_id, idempotent=False)

	_validate_invoice_payload(data)
	si = frappe.new_doc("Sales Invoice")
	_apply_invoice_payload(si, data)

	from custom_erpnext.services.naming_series_service import apply_branch_naming_series

	apply_branch_naming_series(si)

	si.flags.ignore_permissions = True
	si.insert()

	return _finalize_invoice(si, data, sync_key, request_id, idempotent=False)


def _has_full_invoice_payload(data):
	required = ["company", "customer", "branch", "items"]
	return all(data.get(field) for field in required)


def _apply_invoice_payload(si, data):
	si.flags.ignore_permissions = True
	_map_invoice_header(si, data)
	si.set("items", [])
	# Leave payments empty until after set_missing_values(); ERPNext shows an orange
	# "Payment methods refreshed" toast when payments exist before POS profile setup.
	si.set("payments", [])
	_map_invoice_items(si, data.get("items") or [])
	_apply_sales_taxes(si, data)


def _resolve_taxes_and_charges(si, data):
	"""Resolve Sales Taxes and Charges Template for POS/API invoices."""
	template = data.get("taxes_and_charges") or si.taxes_and_charges
	if template:
		return template

	pos_profile = data.get("pos_profile") or si.pos_profile
	if not pos_profile and data.get("pos_device"):
		pos_profile = frappe.db.get_value("POS Device", data["pos_device"], "pos_profile")
	if pos_profile:
		template = frappe.db.get_value("POS Profile", pos_profile, "taxes_and_charges")
		if template:
			return template

	company = data.get("company") or si.company
	if not company:
		return None

	template = frappe.db.get_value(
		"Sales Taxes and Charges Template",
		{"company": company, "is_default": 1},
		"name",
	)
	if template:
		return template

	templates = frappe.get_all(
		"Sales Taxes and Charges Template",
		filters={"company": company, "disabled": 0},
		pluck="name",
		order_by="modified desc",
		limit=1,
	)
	return templates[0] if templates else None


def _apply_sales_taxes(si, data):
	"""Populate taxes child table — required by ksa_compliance and POS invoices.

	ERPNext skips ``set_taxes_and_charges()`` when ``is_pos`` is set, so API
	sync must build tax rows explicitly before insert/submit.

	Zero-rated / tax-exempt sales (SRS §4.1 "with or without tax") are honoured
	when the payload sets ``tax_exempt``/``is_tax_exempt``: no tax rows are
	required and totals are computed without VAT.
	"""
	tax_exempt = cint(data.get("tax_exempt") or data.get("is_tax_exempt"))

	template = _resolve_taxes_and_charges(si, data)
	if template and not tax_exempt:
		si.taxes_and_charges = template

	if not si.pos_profile and data.get("pos_device"):
		pos_profile = frappe.db.get_value("POS Device", data["pos_device"], "pos_profile")
		if pos_profile:
			si.pos_profile = pos_profile

	si.set_missing_values()

	if tax_exempt:
		# Strip any template/rows ERPNext may have inferred so the invoice posts
		# at a 0% tax total intentionally rather than failing the guard below.
		si.taxes_and_charges = None
		si.set("taxes", [])
	else:
		si.set_taxes()

		if not si.get("taxes") and si.taxes_and_charges:
			si.append_taxes_from_master()

		if not si.get("taxes"):
			frappe.throw(
				_(
					"No sales tax rows applied. Provide taxes_and_charges in the payload, "
					"set tax_exempt for zero-rated sales, or configure a default Sales "
					"Taxes and Charges Template for company {0}."
				).format(si.company)
			)

	_apply_api_payments(si, data)
	si.calculate_taxes_and_totals()


def _apply_api_payments(si, data):
	"""Apply middleware payment rows after ERPNext POS profile setup.

	Must run after ``set_missing_values()`` so ``update_multi_mode_option`` does
	not treat API-supplied rows as stale Desk data (which triggers an orange toast
	in ``_server_messages``).
	"""
	payments = data.get("payments")
	if not payments:
		return

	si.set("payments", [])
	_map_invoice_payments(si, payments)


def _finalize_invoice(si, data, offline_id, request_id, idempotent):
	"""Submit (if requested) a freshly created or previously-drafted invoice."""
	si.flags.ignore_permissions = True

	if cint(data.get("submit", 1)) and si.docstatus == 0:
		try:
			si.submit()
		except Exception as err:
			error_message = (
				str(err).strip()
				or getattr(frappe.flags, "error_message", None)
				or err.__class__.__name__
			)
			si.db_set(
				{
					"sync_status": "Failed",
					"sync_log": (
						f"Sync failed via middleware. request_id={request_id}. "
						f"error={error_message}"
					),
				}
			)
			result = _invoice_result(
				offline_id,
				si.name,
				idempotent=idempotent,
				sync_status="Failed",
				status="failed",
			)
			result["error"] = error_message
			return result

	si.db_set(
		{
			"sync_status": "Synced",
			"sync_log": f"Synced via middleware. request_id={request_id}",
		}
	)

	return _invoice_result(offline_id, si.name, idempotent=idempotent, sync_status="Synced")


def _invoice_result(offline_id, invoice_name, idempotent, sync_status, status="success"):
	from custom_erpnext.integrations.zatca.utils import get_zatca_payload_for_invoice

	is_pos_transaction = frappe.db.get_value("Sales Invoice", invoice_name, "is_pos_transaction")

	return {
		"offline_invoice_id": offline_id,
		"sales_invoice": invoice_name,
		"status": status,
		"idempotent": idempotent,
		"sync_status": sync_status,
		"is_pos_transaction": cint(is_pos_transaction),
		"zatca": get_zatca_payload_for_invoice(invoice_name),
	}


def _validate_invoice_payload(data):
	required = ["company", "customer", "branch", "items"]
	for field in required:
		if not data.get(field):
			frappe.throw(_("{0} is required").format(field))

	from custom_erpnext.api.validators import validate_branch_access

	validate_branch_access(data["branch"])

	_validate_customer_and_address(data)
	_validate_b2b_online_origin(data)
	_validate_pos_device(data)
	_validate_return_against(data)
	_validate_items(data)


def _validate_b2b_online_origin(data):
	"""SRS §7.3: B2B standard e-invoices cannot be queued for offline sync."""
	customer = data.get("customer")
	if not customer:
		return

	from custom_erpnext.integrations.zatca.utils import is_b2b_customer

	if is_b2b_customer(customer) and not cint(data.get("issued_online")):
		frappe.throw(
			_(
				"B2B e-invoices require an online connection and cannot be issued "
				"from the offline POS. Set issued_online: 1 when the sale is created "
				"while connected."
			)
		)


def _validate_customer_and_address(data):
	customer = data["customer"]
	if not frappe.db.exists("Customer", customer):
		frappe.throw(_("Customer {0} not found").format(customer))

	company = data.get("company")
	if company and not frappe.db.exists("Company", company):
		frappe.throw(_("Company {0} not found").format(company))

	customer_address = data.get("customer_address")
	if customer_address:
		if not frappe.db.exists("Address", customer_address):
			frappe.throw(_("Customer Address {0} not found").format(customer_address))
		if not frappe.db.exists(
			"Dynamic Link",
			{
				"parenttype": "Address",
				"parent": customer_address,
				"link_doctype": "Customer",
				"link_name": customer,
			},
		):
			frappe.throw(
				_("Address {0} is not linked to Customer {1}").format(customer_address, customer)
			)
		return

	from custom_erpnext.integrations.zatca.utils import is_b2b_customer
	from frappe.contacts.doctype.address.address import get_default_address

	if is_b2b_customer(customer) and not get_default_address("Customer", customer):
		frappe.throw(
			_(
				"Customer Address is required for B2B customer {0}. "
				"Provide customer_address in the payload or set a default address on the customer."
			).format(customer)
		)


def _validate_items(data):
	for idx, item in enumerate(data.get("items") or [], start=1):
		item_code = item.get("item_code")
		if not item_code:
			frappe.throw(_("items[{0}].item_code is required").format(idx - 1))
		if not frappe.db.exists("Item", item_code):
			frappe.throw(_("Item {0} not found").format(item_code))


def _validate_pos_device(data):
	device = data.get("pos_device")
	branch = data.get("branch")
	if device:
		if not frappe.db.exists("POS Device", device):
			frappe.throw(_("POS Device {0} not found").format(device))
		device_branch = frappe.db.get_value("POS Device", device, "branch")
		if branch and device_branch and device_branch != branch:
			frappe.throw(
				_("POS Device {0} does not belong to branch {1}").format(device, branch)
			)

	cashier = data.get("cashier")
	if cashier and branch and frappe.db.exists("User", cashier):
		from custom_erpnext.services.branch_permission_service import user_has_branch_access

		if not user_has_branch_access(cashier, branch):
			frappe.throw(
				_("Cashier {0} is not assigned to branch {1}").format(cashier, branch)
			)


def _resolve_warehouse(data):
	warehouse = data.get("warehouse")
	if warehouse:
		return warehouse

	branch = data.get("branch")
	if branch:
		warehouse = frappe.db.get_value("Company Branch", branch, "warehouse")
		if warehouse:
			return warehouse

	device = data.get("pos_device")
	if device:
		return frappe.db.get_value("POS Device", device, "warehouse")

	return None


def _resolve_customer_address(data):
	if data.get("customer_address"):
		return data["customer_address"]

	customer = data.get("customer")
	if not customer:
		return None

	from custom_erpnext.integrations.zatca.utils import is_b2b_customer

	if not is_b2b_customer(customer):
		return None

	from frappe.contacts.doctype.address.address import get_default_address

	return get_default_address("Customer", customer)


def _validate_return_against(data):
	if not cint(data.get("is_return", 0)):
		return

	return_against = data.get("return_against")
	if not return_against:
		# Return without reference is allowed (controlled at POS by password); nothing to verify.
		return

	original = frappe.db.get_value(
		"Sales Invoice",
		return_against,
		["docstatus", "customer", "branch", "is_return"],
		as_dict=True,
	)
	if not original:
		frappe.throw(_("Return Against invoice {0} not found").format(return_against))
	if original.docstatus != 1:
		frappe.throw(_("Return Against invoice {0} must be submitted").format(return_against))
	if original.is_return:
		frappe.throw(_("Cannot create a return against another return ({0})").format(return_against))
	if data.get("customer") and original.customer != data.get("customer"):
		frappe.throw(
			_("Return customer must match original invoice {0}").format(return_against)
		)
	if data.get("branch") and original.branch and original.branch != data.get("branch"):
		frappe.throw(
			_("Return branch must match original invoice {0}").format(return_against)
		)


def _map_invoice_header(si, data):
	is_return = cint(data.get("is_return", 0))
	sync_key, sync_field = _resolve_sync_storage(data)
	is_pos_transaction = data.get("is_pos_transaction")
	if is_pos_transaction is None:
		is_pos_transaction = bool(
			sync_key or data.get("pos_device") or cint(data.get("is_pos", 1))
		)

	si.update(
		{
			"company": data["company"],
			"customer": data["customer"],
			"customer_address": _resolve_customer_address(data),
			"posting_date": data.get("posting_date") or getdate(),
			"due_date": data.get("due_date"),
			"is_pos": cint(data.get("is_pos", 1)),
			"is_pos_transaction": cint(is_pos_transaction),
			"is_return": is_return,
			"return_against": data.get("return_against"),
			"branch": data.get("branch"),
			"cost_center": data.get("cost_center"),
			"pos_device": data.get("pos_device"),
			"cashier": data.get("cashier"),
			"shift_id": data.get("shift_id"),
			"pos_profile": data.get("pos_profile"),
			"offline_invoice_id": sync_key if sync_field == "offline_invoice_id" else None,
			"online_invoice_id": sync_key if sync_field == "online_invoice_id" else None,
			"sync_status": "Pending",
			"set_warehouse": _resolve_warehouse(data),
			"selling_price_list": data.get("price_list"),
			"additional_discount_percentage": flt(data.get("discount_percent")),
			"coupon_code": data.get("coupon_code"),
			"promotion_applied": data.get("promotion_applied"),
			"tabby_reference": data.get("tabby_reference"),
			"tamara_reference": data.get("tamara_reference"),
			"wallet_amount": flt(data.get("wallet_amount")),
			"remarks": data.get("remarks"),
			"internal_notes": data.get("internal_notes"),
			"payment_method": data.get("payment_method"),
			"sales_representative": data.get("sales_representative"),
			"payment_terms_template": data.get("payment_terms_template"),
		}
	)

	# ZATCA needs an instruction note on credit notes; ksa_compliance reads
	# custom_return_reason, so mirror the retail return_reason into both.
	if is_return and data.get("return_reason"):
		si.return_reason = data["return_reason"]
		if si.meta.get_field("custom_return_reason"):
			si.custom_return_reason = data["return_reason"]

	loyalty_points = cint(data.get("loyalty_points_used"))
	if loyalty_points:
		si.redeem_loyalty_points = 1
		si.loyalty_points = loyalty_points
		si.loyalty_amount = flt(data.get("loyalty_points_value"))

	if not si.pos_profile and data.get("pos_device"):
		pos_profile = frappe.db.get_value("POS Device", data["pos_device"], "pos_profile")
		if pos_profile:
			si.pos_profile = pos_profile


def _map_invoice_items(si, items):
	# Returns/credit notes require negative quantities in ERPNext. Normalise the
	# sign here so the POS can send either positive or negative figures.
	sign = -1 if si.is_return else 1
	for item in items:
		qty = abs(flt(item.get("qty"))) * sign
		si.append(
			"items",
			{
				"item_code": item["item_code"],
				"qty": qty,
				"rate": flt(item.get("rate")),
				"discount_percentage": flt(item.get("discount_percentage")),
				"warehouse": item.get("warehouse") or si.set_warehouse,
				"uom": item.get("uom"),
				"description": item.get("description"),
			},
		)


def _map_invoice_payments(si, payments):
	# POS returns require negative payment amounts (ERPNext
	# verify_payment_amount_is_negative). Normalise to match the invoice sign.
	sign = -1 if si.is_return else 1
	for payment in payments:
		si.append(
			"payments",
			{
				"mode_of_payment": payment["mode_of_payment"],
				"amount": abs(flt(payment.get("amount"))) * sign,
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


def reconcile_stock_quantities(stock_updates, warehouse=None, apply=False):
	"""Compare POS stock against ERP and optionally apply the correction.

	By default this is a read-only variance report (POS qty vs ERP ``actual_qty``).
	When ``apply`` is truthy, a submitted Stock Reconciliation is created for the
	lines that differ, so the endpoint can actually correct ERP stock instead of
	only reporting drift.
	"""
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

	reconciliation = None
	if cint(apply):
		with middleware_sync_context():
			reconciliation = _apply_stock_reconciliation(warehouse, results)

	return {
		"warehouse": warehouse,
		"count": len(results),
		"items": results,
		"applied": bool(cint(apply)),
		"stock_reconciliation": reconciliation,
	}


def update_stock_quantities(stock_updates, warehouse=None):
	"""Deprecated alias kept for the Laravel contract — read-only variance report.

	Prefer :func:`reconcile_stock_quantities`, which can also apply corrections.
	"""
	return reconcile_stock_quantities(stock_updates, warehouse=warehouse, apply=False)


def _apply_stock_reconciliation(warehouse, results):
	"""Create + submit a Stock Reconciliation for lines whose qty differs."""
	rows = [row for row in results if abs(flt(row["variance"])) > 0.0001]
	if not rows:
		return None

	company = frappe.db.get_value("Warehouse", warehouse, "company")
	if not company:
		frappe.throw(_("Warehouse {0} has no company configured").format(warehouse))

	recon = frappe.new_doc("Stock Reconciliation")
	recon.purpose = "Stock Reconciliation"
	recon.company = company
	for row in rows:
		recon.append(
			"items",
			{
				"item_code": row["item_code"],
				"warehouse": warehouse,
				"qty": flt(row["pos_qty"]),
			},
		)

	recon.flags.ignore_permissions = True
	recon.insert(ignore_permissions=True)
	recon.flags.ignore_permissions = True
	recon.submit()
	return recon.name
