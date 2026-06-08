# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import now_datetime


def check_item_reorder_levels():
	"""Create Material Requests for items below reorder level when auto_create_pr is enabled."""
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
			"custom_erpnext.services.reorder_service.create_purchase_material_request",
			queue="long",
			item_code=row.item_code,
			warehouse=row.warehouse,
			qty=row.warehouse_reorder_qty or row.warehouse_reorder_level,
			job_id=f"auto-pr-{row.item_code}-{row.warehouse}",
			deduplicate=True,
		)


def create_purchase_material_request(item_code, warehouse, qty):
	item = frappe.get_doc("Item", item_code)
	company = frappe.db.get_value("Warehouse", warehouse, "company")
	if not company:
		return

	mr = frappe.new_doc("Material Request")
	mr.material_request_type = "Purchase"
	mr.company = company
	mr.set_warehouse = warehouse
	mr.schedule_date = now_datetime()
	mr.auto_created_via_reorder = 1
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
		"Auto Material Request %s created for %s @ %s", mr.name, item_code, warehouse
	)
