# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import cint, flt, get_datetime


def get_modified_filter(modified_from):
	if not modified_from:
		return {}
	try:
		return {"modified": [">=", get_datetime(modified_from)]}
	except Exception as err:
		frappe.throw(f"Invalid modified_from: {modified_from}")


def get_branch_context(branch):
	branch_doc = frappe.get_doc("Company Branch", branch)
	return {
		"branch": branch_doc.name,
		"company": branch_doc.company,
		"warehouse": branch_doc.warehouse,
		"cost_center": branch_doc.cost_center,
	}


def fetch_items_for_pos(branch, modified_from=None, page=1, page_size=100, price_list=None):
	context = get_branch_context(branch)
	filters = {"disabled": 0, **get_modified_filter(modified_from)}

	total = frappe.db.count("Item", filters)
	offset = (page - 1) * page_size
	items = frappe.get_all(
		"Item",
		filters=filters,
		fields=[
			"name as item_code",
			"item_name",
			"item_group",
			"stock_uom",
			"standard_rate",
			"is_stock_item",
			"brand",
			"weight_per_unit",
			"item_type",
			"is_composite",
			"composite_bundle",
			"max_discount",
			"secondary_barcode",
			"barcode_symbology",
			"is_weight_based",
			"min_selling_price",
			"max_selling_price",
			"is_eligible_for_loyalty",
			"points_per_purchase",
			"modified",
		],
		order_by="modified asc",
		limit_page_length=page_size,
		limit_start=offset,
	)

	item_codes = [row.item_code for row in items]
	barcodes = _get_item_barcodes(item_codes)
	prices = _get_item_prices(item_codes, price_list, context["company"])

	for row in items:
		row["barcodes"] = barcodes.get(row.item_code, [])
		row["item_prices"] = prices.get(row.item_code, [])
		row["branch"] = branch
		row["company"] = context["company"]

	return items, total, context


def pull_items(modified_from=None, page=1, page_size=100):
	filters = {"disabled": 0, **get_modified_filter(modified_from)}
	total = frappe.db.count("Item", filters)
	offset = (page - 1) * page_size
	records = frappe.get_all(
		"Item",
		filters=filters,
		fields=[
			"name as item_code",
			"item_name",
			"item_group",
			"stock_uom",
			"standard_rate",
			"disabled",
			"is_stock_item",
			"item_type",
			"modified",
		],
		order_by="modified asc",
		limit_page_length=page_size,
		limit_start=offset,
	)
	return records, total


def pull_item_prices(company=None, modified_from=None, page=1, page_size=200):
	filters = get_modified_filter(modified_from)
	if company:
		selling_lists = frappe.get_all(
			"Price List",
			filters={"selling": 1, "enabled": 1},
			pluck="name",
		)
		if selling_lists:
			filters["price_list"] = ["in", selling_lists]
	total = frappe.db.count("Item Price", filters)
	offset = (page - 1) * page_size
	records = frappe.get_all(
		"Item Price",
		filters=filters,
		fields=[
			"name",
			"item_code",
			"price_list",
			"currency",
			"price_list_rate",
			"valid_from",
			"valid_upto",
			"modified",
		],
		order_by="modified asc",
		limit_page_length=page_size,
		limit_start=offset,
	)
	return records, total


def pull_customers(company=None, branch=None, modified_from=None, page=1, page_size=100):
	filters = {"disabled": 0, **get_modified_filter(modified_from)}
	if branch:
		filters["branch"] = branch

	total = frappe.db.count("Customer", filters)
	offset = (page - 1) * page_size
	records = frappe.get_all(
		"Customer",
		filters=filters,
		fields=[
			"name as customer",
			"customer_name",
			"customer_group",
			"territory",
			"customer_type",
			"tax_id",
			"branch",
			"customer_code",
			"party_account",
			"max_discount_percent",
			"credit_days",
			"loyalty_program",
			"default_price_list",
			"modified",
		],
		order_by="modified asc",
		limit_page_length=page_size,
		limit_start=offset,
	)
	return records, total


def pull_tax_templates(modified_from=None, page=1, page_size=50):
	filters = get_modified_filter(modified_from)
	total = frappe.db.count("Sales Taxes and Charges Template", filters)
	offset = (page - 1) * page_size
	templates = frappe.get_all(
		"Sales Taxes and Charges Template",
		filters=filters,
		fields=["name", "title", "company", "is_default", "modified"],
		order_by="modified asc",
		limit_page_length=page_size,
		limit_start=offset,
	)

	for template in templates:
		template["taxes"] = frappe.get_all(
			"Sales Taxes and Charges",
			{"parent": template.name},
			fields=[
				"charge_type",
				"account_head",
				"description",
				"rate",
				"included_in_print_rate",
				"cost_center",
			],
			order_by="idx asc",
		)

	return templates, total


def pull_warehouses(company=None, branch=None, modified_from=None, page=1, page_size=50):
	filters = {"disabled": 0, **get_modified_filter(modified_from)}
	if company:
		filters["company"] = company
	if branch:
		filters["branch"] = branch

	total = frappe.db.count("Warehouse", filters)
	offset = (page - 1) * page_size
	records = frappe.get_all(
		"Warehouse",
		filters=filters,
		fields=[
			"name as warehouse",
			"warehouse_name",
			"company",
			"branch",
			"retail_warehouse_type",
			"is_pos_warehouse",
			"parent_warehouse",
			"modified",
		],
		order_by="modified asc",
		limit_page_length=page_size,
		limit_start=offset,
	)
	return records, total


def pull_stock(warehouse=None, branch=None, modified_from=None, page=1, page_size=200):
	if not warehouse and branch:
		warehouse = frappe.db.get_value("Company Branch", branch, "warehouse")

	if not warehouse:
		frappe.throw("warehouse or branch is required")

	filters = {"warehouse": warehouse}
	if modified_from:
		# Bin has no modified - use stock ledger or item modified as proxy
		pass

	total = frappe.db.count("Bin", filters)
	offset = (page - 1) * page_size
	records = frappe.get_all(
		"Bin",
		filters=filters,
		fields=["item_code", "warehouse", "actual_qty", "reserved_qty", "projected_qty"],
		order_by="item_code asc",
		limit_page_length=page_size,
		limit_start=offset,
	)
	return records, total, warehouse


def pull_promotions(branch=None, modified_from=None, page=1, page_size=50):
	filters = {"is_active": 1, **get_modified_filter(modified_from)}
	total = frappe.db.count("Promotion Rule", filters)
	offset = (page - 1) * page_size
	records = frappe.get_all(
		"Promotion Rule",
		filters=filters,
		fields=[
			"name",
			"promotion_name",
			"promotion_code",
			"promotion_type",
			"start_date",
			"end_date",
			"discount_percent",
			"fixed_amount",
			"buy_qty",
			"get_qty",
			"coupon_code",
			"modified",
		],
		order_by="modified asc",
		limit_page_length=page_size,
		limit_start=offset,
	)

	if branch:
		filtered = []
		for promo in records:
			branches = frappe.get_all(
				"Promotion Branch",
				{"parent": promo.name, "branch": branch, "is_active": 1},
				pluck="name",
			)
			if branches or not frappe.db.count("Promotion Branch", {"parent": promo.name}):
				filtered.append(promo)
		return filtered, len(filtered)

	return records, total


def pull_branches(company=None, modified_from=None):
	filters = {"is_active": 1, **get_modified_filter(modified_from)}
	if company:
		filters["company"] = company
	return frappe.get_all(
		"Company Branch",
		filters=filters,
		fields=[
			"name as branch",
			"branch_name",
			"branch_code",
			"company",
			"cost_center",
			"warehouse",
			"modified",
		],
		order_by="branch_name asc",
	)


def _get_item_barcodes(item_codes):
	if not item_codes:
		return {}
	rows = frappe.get_all(
		"Item Barcode",
		filters={"parent": ["in", item_codes]},
		fields=["parent", "barcode", "barcode_type", "uom"],
	)
	result = {}
	for row in rows:
		result.setdefault(row.parent, []).append(
			{"barcode": row.barcode, "barcode_type": row.barcode_type, "uom": row.uom}
		)
	return result


def _get_item_prices(item_codes, price_list, company):
	if not item_codes:
		return {}

	filters = {"item_code": ["in", item_codes]}
	if price_list:
		filters["price_list"] = price_list

	rows = frappe.get_all(
		"Item Price",
		filters=filters,
		fields=["item_code", "price_list", "currency", "price_list_rate", "valid_from", "valid_upto"],
	)
	result = {}
	for row in rows:
		result.setdefault(row.item_code, []).append(row)
	return result
