# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt, now_datetime


def check_item_reorder_levels():
	"""Create reorder requests for items below their reorder level (SRS §3.13).

	When ``auto_create_pr`` is enabled the system raises a Material Request,
	preferring an inter-branch transfer when surplus stock exists elsewhere and
	otherwise a purchase request with a suggested supplier.
	"""
	items = frappe.db.sql(
		"""
		select parent as item_code, warehouse, warehouse_reorder_level, warehouse_reorder_qty
		from `tabItem Reorder`
		where warehouse_reorder_level > 0 and auto_create_pr = 1
		""",
		as_dict=True,
	)

	for row in items:
		balance = frappe.db.get_value(
			"Bin", {"item_code": row.item_code, "warehouse": row.warehouse}, "actual_qty"
		) or 0

		if balance > row.warehouse_reorder_level:
			continue

		frappe.enqueue(
			"custom_erpnext.services.reorder_service.create_reorder_request",
			queue="long",
			item_code=row.item_code,
			warehouse=row.warehouse,
			qty=row.warehouse_reorder_qty or row.warehouse_reorder_level,
			job_id=f"auto-pr-{row.item_code}-{row.warehouse}",
			deduplicate=True,
		)


def get_default_supplier(item_code):
	"""Suggest a supplier for an item: Item Default first, then Item Supplier."""
	supplier = frappe.db.get_value("Item Default", {"parent": item_code}, "default_supplier")
	if supplier:
		return supplier
	return frappe.db.get_value("Item Supplier", {"parent": item_code}, "supplier")


def find_transfer_source(item_code, needed_qty, exclude_warehouse=None, company=None):
	"""Find a same-company warehouse with enough surplus to fulfil a transfer.

	Surplus respects the source warehouse's own reorder level so we never drain a
	branch below its buffer. Returns the warehouse with the largest surplus.
	"""
	bins = frappe.get_all(
		"Bin",
		filters={"item_code": item_code, "actual_qty": [">", 0]},
		fields=["warehouse", "actual_qty"],
	)

	best = None
	for row in bins:
		if exclude_warehouse and row.warehouse == exclude_warehouse:
			continue

		wh = frappe.db.get_value(
			"Warehouse", row.warehouse, ["company", "disabled"], as_dict=True
		)
		if not wh or wh.disabled:
			continue
		if company and wh.company != company:
			continue

		source_level = (
			frappe.db.get_value(
				"Item Reorder",
				{"parent": item_code, "warehouse": row.warehouse},
				"warehouse_reorder_level",
			)
			or 0
		)
		available = flt(row.actual_qty) - flt(source_level)
		if available >= flt(needed_qty) and (not best or available > best["available"]):
			best = {"warehouse": row.warehouse, "available": available}

	return best


def decide_reorder_action(needed_qty, transfer_source):
	"""Choose 'transfer' when a viable surplus source exists, else 'purchase'."""
	if transfer_source and flt(transfer_source.get("available")) >= flt(needed_qty):
		return "transfer"
	return "purchase"


def create_reorder_request(item_code, warehouse, qty):
	item = frappe.get_doc("Item", item_code)
	company = frappe.db.get_value("Warehouse", warehouse, "company")
	if not company:
		return None

	source = find_transfer_source(item_code, qty, exclude_warehouse=warehouse, company=company)
	action = decide_reorder_action(qty, source)

	mr = frappe.new_doc("Material Request")
	mr.company = company
	mr.schedule_date = now_datetime()
	mr.auto_created_via_reorder = 1
	if mr.meta.has_field("source_item"):
		mr.source_item = item_code

	if action == "transfer":
		mr.material_request_type = "Material Transfer"
		mr.set_from_warehouse = source["warehouse"]
		mr.set_warehouse = warehouse
		mr.append(
			"items",
			{
				"item_code": item_code,
				"qty": qty,
				"warehouse": warehouse,
				"from_warehouse": source["warehouse"],
				"uom": item.stock_uom,
				"schedule_date": mr.schedule_date,
			},
		)
	else:
		mr.material_request_type = "Purchase"
		mr.set_warehouse = warehouse
		supplier = get_default_supplier(item_code)
		if supplier and mr.meta.has_field("auto_suggested_supplier"):
			mr.auto_suggested_supplier = supplier
		mr.append(
			"items",
			{
				"item_code": item_code,
				"qty": qty,
				"warehouse": warehouse,
				"uom": item.stock_uom,
				"schedule_date": mr.schedule_date,
			},
		)

	mr.insert(ignore_permissions=True)

	frappe.logger("custom_erpnext").info(
		"Auto reorder %s (%s) created for %s @ %s", mr.name, action, item_code, warehouse
	)
	return mr.name


def create_purchase_material_request(item_code, warehouse, qty):
	"""Deprecated alias retained for backwards compatibility."""
	return create_reorder_request(item_code, warehouse, qty)
