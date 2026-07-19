# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import cint, flt, get_datetime


def _branch_clause(branch):
	"""Build a ``frappe.get_all`` filter value for a branch scope.

	Accepts a single branch name (equality) or a list/tuple/set of names
	(``IN`` clause), so endpoints can scope a read to all branches a restricted
	caller is allowed to see.
	"""
	if isinstance(branch, (list, tuple, set)):
		return ["in", list(branch)]
	return branch


def get_modified_filter(modified_from):
	if not modified_from:
		return {}
	try:
		parsed = get_datetime(modified_from)
	except Exception:
		parsed = None
	if not parsed:
		# Reject unparseable timestamps with a 422 instead of letting a None/garbage
		# value reach the query layer (SEC-11). Don't echo unbounded client input.
		frappe.throw(frappe._("Invalid modified_from: expected an ISO datetime"))
	return {"modified": [">=", parsed]}


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
			"main_group",
			"sub_group",
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
			"main_group",
			"sub_group",
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


def pull_item_groups(group_type=None, modified_from=None, page=1, page_size=100):
	"""Pull retail Item Groups (main/sub) for middleware sync."""
	filters = get_modified_filter(modified_from)
	if group_type:
		filters["group_type"] = group_type

	total = frappe.db.count("Item Group", filters)
	offset = (page - 1) * page_size
	records = frappe.get_all(
		"Item Group",
		filters=filters,
		fields=[
			"name as item_group",
			"item_group_name",
			"parent_item_group",
			"is_group",
			"group_type",
			"parent_main_group",
			"default_margin",
			"commission_rate",
			"category_code",
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
			"buying",
			"selling",
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
	if branch is not None:
		filters["branch"] = _branch_clause(branch)

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
			filters={"parent": template.name},
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
	if branch is not None:
		filters["branch"] = _branch_clause(branch)

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
	# Bin.modified advances on every stock movement, so it is a reliable cursor
	# for incremental stock sync (SRS §5.1 "incremental"). Order by modified so
	# pagination over an incremental window stays stable.
	if modified_from:
		filters.update(get_modified_filter(modified_from))

	total = frappe.db.count("Bin", filters)
	offset = (page - 1) * page_size
	records = frappe.get_all(
		"Bin",
		filters=filters,
		fields=[
			"item_code",
			"warehouse",
			"actual_qty",
			"reserved_qty",
			"projected_qty",
			"modified",
		],
		order_by="modified asc",
		limit_page_length=page_size,
		limit_start=offset,
	)
	return records, total, warehouse


def pull_promotions(branch=None, modified_from=None, page=1, page_size=50):
	filters = {"is_active": 1, **get_modified_filter(modified_from)}

	# Resolve branch visibility before pagination so `total` and page slices stay
	# correct (SRS §5.1). Post-page Python filtering used to under-count totals and
	# drop branch promotions that lived on later DB pages.
	if branch:
		qualifying = _qualifying_promotion_names(branch, dict(filters))
		if not qualifying:
			return [], 0
		filters["name"] = ["in", qualifying]

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

	return records, total


def _qualifying_promotion_names(branch, base_filters):
	"""Promotion names visible to a branch.

	A promotion is visible when it is global (no Applicable Branches rows) or has
	an active Promotion Branch row for the requested branch. Computed up-front so
	the caller can paginate at the DB level with correct totals.
	"""
	active_names = frappe.get_all("Promotion Rule", filters=base_filters, pluck="name")
	if not active_names:
		return []

	restricted = set(
		frappe.get_all(
			"Promotion Branch",
			filters={"parent": ["in", active_names], "parenttype": "Promotion Rule"},
			pluck="parent",
			distinct=True,
		)
	)
	allowed = set(
		frappe.get_all(
			"Promotion Branch",
			filters={
				"parent": ["in", active_names],
				"parenttype": "Promotion Rule",
				"branch": branch,
				"is_active": 1,
			},
			pluck="parent",
		)
	)
	return [name for name in active_names if name not in restricted or name in allowed]


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


def pull_discounts(branch=None, modified_from=None, page=1, page_size=100):
	"""Pull user discount profiles and POS profile discount limits for POS sync."""
	filters = get_modified_filter(modified_from)
	profiles = frappe.get_all(
		"User Discount Profile",
		filters=filters,
		fields=[
			"name",
			"user",
			"max_discount_percent",
			"require_approval_above",
			"approval_authority",
			"is_cashier",
			"is_branch_manager",
			"modified",
		],
		order_by="modified asc",
		ignore_permissions=True,
	)

	for profile in profiles:
		user_fields = frappe.db.get_value(
			"User",
			profile.user,
			["employee_id", "branch", "max_discount", "cashier_number", "first_name", "last_name"],
			as_dict=True,
		) or {}
		profile["employee_id"] = user_fields.get("employee_id")
		profile["branch"] = user_fields.get("branch")
		profile["user_max_discount"] = flt(user_fields.get("max_discount"))
		profile["cashier_number"] = user_fields.get("cashier_number")
		profile["full_name"] = " ".join(
			part for part in (user_fields.get("first_name"), user_fields.get("last_name")) if part
		)
		profile["allowed_branches"] = frappe.get_all(
			"User Branch Assignment",
			filters={"parent": profile.name},
			fields=["branch", "is_default"],
			ignore_permissions=True,
		)
		profile["effective_max_discount_percent"] = flt(profile.max_discount_percent) or profile["user_max_discount"]

	if branch:
		profiles = _filter_discount_profiles_by_branch(profiles, branch)

	pos_profile_discounts = _pull_pos_profile_discounts(branch)
	total = len(profiles)
	offset = (page - 1) * page_size
	return profiles[offset : offset + page_size], total, pos_profile_discounts


def pull_employees(company=None, branch=None, modified_from=None, page=1, page_size=100):
	"""Pull employees and POS users for middleware sync."""
	emp_filters = {"status": "Active", **get_modified_filter(modified_from)}
	if company:
		emp_filters["company"] = company

	employees = frappe.get_all(
		"Employee",
		filters=emp_filters,
		fields=[
			"name",
			"employee_name",
			"employee_number",
			"user_id",
			"company",
			"designation",
			"department",
			"cell_number",
			"company_email",
			"status",
			"modified",
		],
		order_by="modified asc",
		ignore_permissions=True,
	)

	records = []
	linked_users = set()
	for row in employees:
		record = {
			"employee": row.name,
			"employee_name": row.employee_name,
			"employee_number": row.employee_number,
			"user_id": row.user_id,
			"company": row.company,
			"designation": row.designation,
			"department": row.department,
			"cell_number": row.cell_number,
			"company_email": row.company_email,
			"status": row.status,
			"modified": row.modified,
			"source": "Employee",
		}
		if row.user_id:
			linked_users.add(row.user_id)
			_enrich_employee_user_fields(record, row.user_id)
		records.append(record)

	user_filters = {"enabled": 1, "pos_access": 1, **get_modified_filter(modified_from)}
	pos_users = frappe.get_all(
		"User",
		filters=user_filters,
		fields=[
			"name",
			"first_name",
			"last_name",
			"employee_id",
			"branch",
			"max_discount",
			"cashier_number",
			"pos_access",
			"modified",
		],
		order_by="modified asc",
		ignore_permissions=True,
	)

	for user in pos_users:
		if user.name in linked_users:
			continue
		records.append(
			{
				"employee": user.employee_id or user.name,
				"employee_name": " ".join(part for part in (user.first_name, user.last_name) if part),
				"employee_number": user.cashier_number,
				"user_id": user.name,
				"branch": user.branch,
				"max_discount": flt(user.max_discount),
				"cashier_number": user.cashier_number,
				"pos_access": user.pos_access,
				"modified": user.modified,
				"source": "User",
			}
		)

	if branch is not None:
		allowed = set(branch) if isinstance(branch, (list, tuple, set)) else {branch}
		records = [
			row
			for row in records
			if not row.get("branch") or row.get("branch") in allowed
		]

	records.sort(key=lambda row: row.get("modified") or "")
	total = len(records)
	offset = (page - 1) * page_size
	return records[offset : offset + page_size], total


def pull_system_settings(branch=None, company=None, modified_from=None):
	"""Pull POS system settings bundle for middleware / day-open full sync."""
	context = {}
	if branch:
		context = get_branch_context(branch)
		company = company or context.get("company")

	branches = pull_branches(company, modified_from)
	pos_devices = _pull_pos_devices_settings(branch, modified_from)
	tax_templates, _tax_total = pull_tax_templates(modified_from, page=1, page_size=500)
	employees, _emp_total = pull_employees(company=company, branch=branch, modified_from=modified_from, page=1, page_size=500)
	payment_methods = _pull_payment_method_configs(branch, modified_from)
	warehouses, _wh_total = pull_warehouses(company=company, branch=branch, modified_from=modified_from, page=1, page_size=100)

	return {
		"branch": branch,
		"company": company,
		"context": context,
		"branches": branches,
		"pos_devices": pos_devices,
		"tax_templates": tax_templates,
		"employees": employees,
		"payment_methods": payment_methods,
		"warehouses": warehouses,
	}


def full_sync(branch, price_list=None, page=1, page_size=500):
	"""Bundle master data for day-open full sync (SRS §5.1.2)."""
	context = get_branch_context(branch)
	company = context["company"]

	items, items_total, item_context = fetch_items_for_pos(
		branch=branch,
		modified_from=None,
		page=page,
		page_size=page_size,
		price_list=price_list,
	)
	prices, prices_total = pull_item_prices(company=company, modified_from=None, page=page, page_size=page_size)
	customers, customers_total = pull_customers(
		company=company, branch=branch, modified_from=None, page=page, page_size=page_size
	)
	promotions, promotions_total = pull_promotions(branch=branch, modified_from=None, page=page, page_size=page_size)
	discounts, discounts_total, pos_profile_discounts = pull_discounts(
		branch=branch, modified_from=None, page=page, page_size=page_size
	)
	stock, stock_total, warehouse_name = pull_stock(
		branch=branch, modified_from=None, page=page, page_size=page_size
	)
	system_settings = pull_system_settings(branch=branch, company=company, modified_from=None)

	return {
		"sync_type": "full",
		"branch": branch,
		"company": company,
		"context": item_context,
		"warehouse": warehouse_name,
		"items": items,
		"prices": prices,
		"customers": customers,
		"promotions": promotions,
		"discounts": discounts,
		"pos_profile_discounts": pos_profile_discounts,
		"stock": stock,
		"system_settings": system_settings,
		"totals": {
			"items": items_total,
			"prices": prices_total,
			"customers": customers_total,
			"promotions": promotions_total,
			"discounts": discounts_total,
			"stock": stock_total,
		},
		"page": page,
		"page_size": page_size,
	}


def _pull_pos_devices_settings(branch=None, modified_from=None):
	filters = {"is_active": 1, **get_modified_filter(modified_from)}
	if branch:
		filters["branch"] = branch
	return frappe.get_all(
		"POS Device",
		filters=filters,
		fields=[
			"name",
			"device_id",
			"device_name",
			"branch",
			"warehouse",
			"pos_profile",
			"device_type",
			"last_sync_time",
			"is_online",
			"modified",
		],
		order_by="modified asc",
	)


def _pull_payment_method_configs(branch=None, modified_from=None):
	filters = {"is_active": 1, **get_modified_filter(modified_from)}
	if branch:
		filters["branch"] = branch
	return frappe.get_all(
		"Payment Method Config",
		filters=filters,
		fields=[
			"name",
			"branch",
			"payment_method",
			"is_active",
			"requires_internet",
			"sandbox_mode",
			"min_amount",
			"max_amount",
			"commission_rate",
			"settlement_period_days",
			"modified",
		],
		order_by="modified asc",
		ignore_permissions=True,
	)


def _pull_pos_profile_discounts(branch=None):
	filters = {"disabled": 0}
	if branch:
		filters["branch"] = branch
	return frappe.get_all(
		"POS Profile",
		filters=filters,
		fields=[
			"name",
			"branch",
			"max_discount_percent",
			"require_manager_approval_for_discount",
			"modified",
		],
		ignore_permissions=True,
	)


def _filter_discount_profiles_by_branch(profiles, branch):
	filtered = []
	for profile in profiles:
		allowed = {row.branch for row in profile.get("allowed_branches") or []}
		if not allowed or branch in allowed or profile.get("branch") == branch:
			filtered.append(profile)
	return filtered


def _enrich_employee_user_fields(record, user_id):
	user_fields = frappe.db.get_value(
		"User",
		user_id,
		["employee_id", "branch", "max_discount", "cashier_number", "pos_access"],
		as_dict=True,
	) or {}
	record.update(
		{
			"employee_id": user_fields.get("employee_id"),
			"branch": user_fields.get("branch"),
			"max_discount": flt(user_fields.get("max_discount")),
			"cashier_number": user_fields.get("cashier_number"),
			"pos_access": user_fields.get("pos_access"),
		}
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
		fields=[
			"item_code",
			"price_list",
			"currency",
			"price_list_rate",
			"buying",
			"selling",
			"valid_from",
			"valid_upto",
		],
	)
	result = {}
	for row in rows:
		result.setdefault(row.item_code, []).append(row)
	return result
