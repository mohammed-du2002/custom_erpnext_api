# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import cint

BRANCH_ISOLATED_DOCTYPES = [
	"Company Branch",
	"Branch Section",
	"Sales Invoice",
	"Material Request",
	"Purchase Order",
	"Purchase Invoice",
	"Purchase Receipt",
	"Landed Cost Voucher",
	"POS Profile",
	"Warehouse",
	"Customer",
	"Supplier",
	"Daily Sales Summary",
	"POS Cashier Shift",
	"Cashier Movement",
	"POS Device",
	"Payment Method Config",
	"Party Account Mapping",
	"User Activity Monitor",
	"Stock Transfer Request",
]

BRANCH_VALIDATE_DOCTYPES = [
	"Sales Invoice",
	"Material Request",
	"Purchase Order",
	"Purchase Invoice",
	"Purchase Receipt",
	"Landed Cost Voucher",
	"POS Profile",
	"Warehouse",
	"Customer",
	"Supplier",
	"Daily Sales Summary",
	"POS Cashier Shift",
	"Cashier Movement",
	"POS Device",
	"Payment Method Config",
	"Party Account Mapping",
	"User Activity Monitor",
	"Branch Section",
	"Stock Transfer Request",
]

BYPASS_ROLES = ("System Manager",)


def bypass_branch_restrictions(user=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return any(role in BYPASS_ROLES for role in frappe.get_roles(user))


def get_user_branches(user=None):
	user = user or frappe.session.user
	if bypass_branch_restrictions(user):
		return frappe.get_all("Company Branch", {"is_active": 1}, pluck="name")

	branches = frappe.get_all(
		"User Permission",
		filters={"user": user, "allow": "Company Branch"},
		pluck="for_value",
	)
	if branches:
		return branches

	profile_name = frappe.db.get_value("User Discount Profile", {"user": user}, "name")
	if profile_name:
		branches = frappe.get_all(
			"User Branch Assignment",
			filters={"parent": profile_name},
			pluck="branch",
		)
		if branches:
			return branches

	user_branch = frappe.db.get_value("User", user, "branch")
	return [user_branch] if user_branch else []


def get_default_branch(user=None):
	user = user or frappe.session.user

	default = frappe.db.get_value(
		"User Permission",
		{"user": user, "allow": "Company Branch", "is_default": 1},
		"for_value",
	)
	if default:
		return default

	profile_name = frappe.db.get_value("User Discount Profile", {"user": user}, "name")
	if profile_name:
		default = frappe.db.get_value(
			"User Branch Assignment",
			{"parent": profile_name, "is_default": 1},
			"branch",
		)
		if default:
			return default

	return frappe.db.get_value("User", user, "branch")


def user_has_branch_access(user, branch):
	if not branch:
		return True
	if bypass_branch_restrictions(user):
		return True
	return branch in get_user_branches(user)


def get_permission_query_conditions(user, doctype=None):
	if bypass_branch_restrictions(user):
		return ""

	branches = get_user_branches(user)
	if not branches:
		return "1=0"

	if doctype == "Company Branch":
		return f"`tabCompany Branch`.name in {_sql_in(branches)}"

	if doctype == "Branch Section":
		return f"`tabBranch Section`.branch in {_sql_in(branches)}"

	if doctype == "Stock Transfer Request":
		warehouses = frappe.get_all(
			"Warehouse",
			filters={"branch": ["in", branches]},
			pluck="name",
		)
		if not warehouses:
			return "1=0"
		warehouse_list = _sql_in(warehouses)
		return (
			f"(`tabStock Transfer Request`.from_warehouse in {warehouse_list} "
			f"or `tabStock Transfer Request`.to_warehouse in {warehouse_list})"
		)

	meta = frappe.get_meta(doctype)
	if meta.has_field("branch"):
		branch_list = _sql_in(branches)
		if doctype in ("Customer", "Supplier"):
			return (
				f"(`tab{doctype}`.branch in {branch_list} "
				f"OR IFNULL(`tab{doctype}`.branch, '') = '')"
			)
		return f"`tab{doctype}`.branch in {branch_list}"

	return ""


def has_branch_permission(doc, ptype=None, user=None, debug=False):
	user = user or frappe.session.user
	if bypass_branch_restrictions(user):
		return True

	if getattr(frappe.local, "middleware_sync", False):
		return True

	if doc.doctype == "Company Branch":
		return user_has_branch_access(user, doc.name)

	if doc.doctype == "Branch Section":
		branch = doc.get("branch")
		return not branch or user_has_branch_access(user, branch)

	if doc.doctype == "Stock Transfer Request":
		return _stock_transfer_has_permission(doc, user)

	branch = doc.get("branch")
	if not branch:
		# Shared walk-in parties without branch must remain readable for POS/API flows.
		if doc.doctype in ("Customer", "Supplier") and ptype in ("read", "select"):
			return bool(get_user_branches(user))
		return ptype in ("create", "write")

	return user_has_branch_access(user, branch)


def validate_document_branch(doc, method=None):
	user = frappe.session.user
	if bypass_branch_restrictions(user):
		return

	if doc.doctype == "Material Request":
		_validate_material_request(doc, user)
		return

	if doc.doctype == "Stock Transfer Request":
		_validate_stock_transfer_request(doc, user)
		return

	if doc.doctype == "Branch Section":
		if doc.branch and not user_has_branch_access(user, doc.branch):
			frappe.throw(_("Not permitted to access branch {0}").format(doc.branch))
		return

	if not doc.meta.has_field("branch"):
		return

	if not doc.get("branch"):
		default_branch = get_default_branch(user)
		if default_branch:
			doc.branch = default_branch
		return

	if not user_has_branch_access(user, doc.branch):
		frappe.throw(_("Not permitted to access branch {0}").format(doc.branch))


def sync_user_branch_permissions(user, branch_rows=None, fallback_branch=None):
	if not user or user in ("Administrator", "Guest"):
		return

	existing = frappe.get_all(
		"User Permission",
		filters={"user": user, "allow": "Company Branch"},
		pluck="name",
	)
	for name in existing:
		frappe.delete_doc("User Permission", name, force=True, ignore_permissions=True)

	rows = branch_rows or []
	if rows:
		for row in rows:
			_create_branch_permission(user, row.get("branch"), row.get("is_default"))
	elif fallback_branch:
		_create_branch_permission(user, fallback_branch, is_default=1)

	frappe.cache.hdel("user_permissions", user)


def sync_profile_branch_permissions(doc, method=None):
	rows = [{"branch": row.branch, "is_default": row.is_default} for row in doc.allowed_branches]
	sync_user_branch_permissions(doc.user, branch_rows=rows)


def sync_user_default_branch(doc, method=None):
	if frappe.db.exists("User Discount Profile", {"user": doc.name}):
		return
	sync_user_branch_permissions(doc.name, fallback_branch=doc.branch)


def _create_branch_permission(user, branch, is_default=0):
	if not branch or not frappe.db.exists("Company Branch", {"name": branch, "is_active": 1}):
		return

	frappe.get_doc(
		{
			"doctype": "User Permission",
			"user": user,
			"allow": "Company Branch",
			"for_value": branch,
			"apply_to_all_doctypes": 1,
			"is_default": cint(is_default),
		}
	).insert(ignore_permissions=True)


def _validate_material_request(doc, user):
	if not doc.get("branch"):
		default_branch = get_default_branch(user)
		if default_branch:
			doc.branch = default_branch

	if doc.branch and not user_has_branch_access(user, doc.branch):
		frappe.throw(_("Not permitted to access branch {0}").format(doc.branch))

	if doc.branch_section and doc.branch:
		section_branch = frappe.db.get_value("Branch Section", doc.branch_section, "branch")
		if section_branch and section_branch != doc.branch:
			frappe.throw(_("Section {0} does not belong to branch {1}").format(doc.branch_section, doc.branch))


def _validate_stock_transfer_request(doc, user):
	for warehouse_field in ("from_warehouse", "to_warehouse"):
		warehouse = doc.get(warehouse_field)
		if not warehouse:
			continue

		warehouse_branch = frappe.db.get_value("Warehouse", warehouse, "branch")
		if warehouse_branch and not user_has_branch_access(user, warehouse_branch):
			frappe.throw(
				_("Warehouse {0} belongs to a branch you cannot access").format(frappe.bold(warehouse))
			)


def _stock_transfer_has_permission(doc, user):
	for warehouse_field in ("from_warehouse", "to_warehouse"):
		warehouse = doc.get(warehouse_field)
		if not warehouse:
			continue

		warehouse_branch = frappe.db.get_value("Warehouse", warehouse, "branch")
		if warehouse_branch and user_has_branch_access(user, warehouse_branch):
			return True

	return not doc.get("from_warehouse") and not doc.get("to_warehouse")


def _sql_in(values):
	if not values:
		return "('')"
	return "(" + ", ".join(frappe.db.escape(value) for value in values) + ")"
