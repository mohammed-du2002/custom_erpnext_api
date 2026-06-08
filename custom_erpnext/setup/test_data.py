# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Seed branch isolation test data for development / QA."""

import frappe
from frappe.utils import getdate, now_datetime

TEST_USERS = [
	{
		"email": "cashier.br1@test.local",
		"first_name": "Cashier",
		"last_name": "BR1",
		"roles": ["Sales User", "Stock User"],
		"branches": [{"branch": "BR1", "is_default": 1}],
		"max_discount_percent": 10,
		"is_cashier": 1,
	},
	{
		"email": "cashier.br2@test.local",
		"first_name": "Cashier",
		"last_name": "BR2",
		"roles": ["Sales User", "Stock User"],
		"branches": [{"branch": "BR2", "is_default": 1}],
		"max_discount_percent": 10,
		"is_cashier": 1,
	},
	{
		"email": "manager.hq@test.local",
		"first_name": "HQ",
		"last_name": "Manager",
		"roles": ["Sales Manager", "Stock Manager", "Purchase Manager"],
		"branches": [
			{"branch": "BR1", "is_default": 1},
			{"branch": "BR2", "is_default": 0},
		],
		"max_discount_percent": 25,
		"is_branch_manager": 1,
		"approval_authority": 1,
	},
]

BRANCHES = [
	{
		"branch_code": "BR1",
		"branch_name": "Riyadh Main Store",
		"warehouse_name": "Stores - BR1",
		"reuse_warehouse": "Stores - T",
	},
	{
		"branch_code": "BR2",
		"branch_name": "Jeddah Store",
		"warehouse_name": "Stores - BR2",
	},
]


def create_branch_isolation_test_data(company=None):
	company = company or _get_company()
	result = {
		"company": company,
		"branches": [],
		"users": [],
		"sales_invoices": [],
		"verification": {},
	}

	for branch_def in BRANCHES:
		result["branches"].append(_ensure_branch(branch_def, company))

	for user_def in TEST_USERS:
		result["users"].append(_ensure_test_user(user_def))

	result["sales_invoices"] = _ensure_sample_sales_invoices(company)
	result["verification"] = verify_branch_isolation()
	frappe.db.commit()
	return result


def verify_branch_isolation():
	from custom_erpnext.services.branch_permission_service import (
		get_permission_query_conditions,
		get_user_branches,
		user_has_branch_access,
	)

	checks = {}
	for email, expected_branches in {
		"cashier.br1@test.local": ["BR1"],
		"cashier.br2@test.local": ["BR2"],
		"manager.hq@test.local": ["BR1", "BR2"],
	}.items():
		if not frappe.db.exists("User", email):
			checks[email] = {"skipped": True}
			continue

		branches = get_user_branches(email)
		perms = frappe.get_all(
			"User Permission",
			filters={"user": email, "allow": "Company Branch"},
			fields=["for_value", "is_default"],
		)
		query = get_permission_query_conditions(email, doctype="Sales Invoice")
		visible = frappe.get_all("Sales Invoice", filters={"branch": ["is", "set"]}, pluck="name")
		if query:
			visible = frappe.db.sql_list(
				f"SELECT name FROM `tabSales Invoice` WHERE branch IS NOT NULL AND branch != '' AND {query}"
			)

		checks[email] = {
			"expected_branches": expected_branches,
			"resolved_branches": branches,
			"branches_ok": sorted(branches) == sorted(expected_branches),
			"user_permissions": perms,
			"permission_query": query,
			"visible_invoices": visible,
			"can_access_br1": user_has_branch_access(email, "BR1"),
			"can_access_br2": user_has_branch_access(email, "BR2"),
		}

	return checks


def _get_company():
	company = frappe.db.get_single_value("Global Defaults", "default_company")
	if company:
		return company
	companies = frappe.get_all("Company", pluck="name", limit=1)
	if not companies:
		frappe.throw("No Company found. Create a Company before running test data setup.")
	return companies[0]


def _ensure_branch(branch_def, company):
	branch_code = branch_def["branch_code"]
	if frappe.db.exists("Company Branch", branch_code):
		return branch_code

	cost_center = frappe.db.get_value(
		"Cost Center", {"company": company, "is_group": 0}, "name", order_by="creation asc"
	)

	doc = frappe.get_doc(
		{
			"doctype": "Company Branch",
			"branch_code": branch_code,
			"branch_name": branch_def["branch_name"],
			"company": company,
			"cost_center": cost_center,
			"is_active": 1,
			"manager_name": f"Manager {branch_code}",
		}
	)
	doc.insert(ignore_permissions=True)

	warehouse = branch_def.get("reuse_warehouse")
	if not warehouse:
		warehouse = _ensure_warehouse(branch_def["warehouse_name"], company)

	frappe.db.set_value("Company Branch", branch_code, "warehouse", warehouse, update_modified=False)
	frappe.db.set_value("Warehouse", warehouse, "branch", branch_code, update_modified=False)

	return branch_code


def _ensure_warehouse(warehouse_name, company):
	existing = frappe.db.get_value("Warehouse", {"warehouse_name": warehouse_name, "company": company})
	if existing:
		return existing

	parent = frappe.db.get_value("Warehouse", {"company": company, "is_group": 1}, "name")
	if not parent:
		parent = frappe.db.get_value("Warehouse", {"company": company}, "name", order_by="lft asc")

	doc = frappe.get_doc(
		{
			"doctype": "Warehouse",
			"warehouse_name": warehouse_name,
			"company": company,
			"parent_warehouse": parent,
			"is_group": 0,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _ensure_test_user(user_def):
	email = user_def["email"]
	if not frappe.db.exists("User", email):
		doc = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": user_def["first_name"],
				"last_name": user_def.get("last_name", ""),
				"send_welcome_email": 0,
				"enabled": 1,
			}
		)
		for role in user_def["roles"]:
			doc.append("roles", {"role": role})
		doc.insert(ignore_permissions=True)
		doc.new_password = "Test@1234"
		doc.save(ignore_permissions=True)

	default_branch = next((row["branch"] for row in user_def["branches"] if row.get("is_default")), None)
	if default_branch:
		frappe.db.set_value("User", email, "branch", default_branch, update_modified=False)

	profile_name = email
	if frappe.db.exists("User Discount Profile", profile_name):
		doc = frappe.get_doc("User Discount Profile", profile_name)
	else:
		doc = frappe.get_doc({"doctype": "User Discount Profile", "user": email})

	doc.max_discount_percent = user_def.get("max_discount_percent", 0)
	doc.is_cashier = user_def.get("is_cashier", 0)
	doc.is_branch_manager = user_def.get("is_branch_manager", 0)
	doc.approval_authority = user_def.get("approval_authority", 0)
	doc.set("allowed_branches", [])
	for row in user_def["branches"]:
		doc.append(
			"allowed_branches",
			{"branch": row["branch"], "is_default": row.get("is_default", 0)},
		)
	doc.save(ignore_permissions=True)

	return {
		"email": email,
		"password": "Test@1234",
		"branches": [row["branch"] for row in user_def["branches"]],
	}


def _ensure_sample_sales_invoices(company):
	customer = _ensure_test_customer(company)
	item = _ensure_test_item(company)
	invoices = []

	for branch_code in ["BR1", "BR2"]:
		offline_id = f"TEST-{branch_code}-001"
		if frappe.db.exists("Sales Invoice", {"offline_invoice_id": offline_id}):
			invoices.append(frappe.db.get_value("Sales Invoice", {"offline_invoice_id": offline_id}, "name"))
			continue

		warehouse = frappe.db.get_value("Company Branch", branch_code, "warehouse")
		si = frappe.new_doc("Sales Invoice")
		si.company = company
		si.customer = customer
		si.branch = branch_code
		si.is_pos = 1
		si.posting_date = getdate()
		si.set_warehouse = warehouse
		si.offline_invoice_id = offline_id
		si.sync_status = "Pending"
		si.append(
			"items",
			{
				"item_code": item,
				"qty": 1,
				"rate": 100,
				"warehouse": warehouse,
			},
		)

		from custom_erpnext.services.naming_series_service import apply_branch_naming_series

		apply_branch_naming_series(si)
		si.flags.ignore_permissions = True
		si.insert()
		invoices.append(si.name)

	return invoices


def _ensure_test_customer(company):
	name = "Test Retail Customer"
	if frappe.db.exists("Customer", name):
		return name

	doc = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": name,
			"customer_type": "Individual",
			"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name") or "Individual",
			"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name") or "All Territories",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _ensure_test_item(company):
	code = "TEST-RETAIL-ITEM"
	if frappe.db.exists("Item", code):
		return code

	doc = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": code,
			"item_name": "Test Retail Item",
			"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name") or "Products",
			"stock_uom": "Nos",
			"is_stock_item": 1,
		}
	)
	doc.insert(ignore_permissions=True)

	if not frappe.db.exists("Item Price", {"item_code": code, "price_list": "Standard Selling"}):
		frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": code,
				"price_list": "Standard Selling",
				"price_list_rate": 100,
			}
		).insert(ignore_permissions=True)

	return code
