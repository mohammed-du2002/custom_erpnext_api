# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _

from custom_erpnext.api.response import error


def parse_json_field(value, fieldname="payload"):
	if value is None:
		return None
	if isinstance(value, (dict, list)):
		return value
	if isinstance(value, str):
		try:
			return json.loads(value)
		except json.JSONDecodeError as err:
			frappe.throw(_("{0} must be valid JSON").format(fieldname))
	frappe.throw(_("{0} has invalid format").format(fieldname))


def validate_pagination(page=None, page_size=None, max_page_size=500):
	page = cint_safe(page, 1)
	page_size = cint_safe(page_size, 100)
	if page < 1:
		frappe.throw(_("page must be >= 1"))
	if page_size < 1 or page_size > max_page_size:
		frappe.throw(_("page_size must be between 1 and {0}").format(max_page_size))
	return page, page_size


def validate_required_fields(data, fields):
	if not isinstance(data, dict):
		frappe.throw(_("Payload must be a JSON object"))

	missing = [field for field in fields if not data.get(field)]
	if missing:
		frappe.throw(_("Missing required fields: {0}").format(", ".join(missing)))


def validate_branch(branch):
	if not branch:
		frappe.throw(_("branch is required"))
	if not frappe.db.exists("Company Branch", {"name": branch, "is_active": 1}):
		frappe.throw(_("Branch {0} not found or inactive").format(branch))


def validate_branch_access(branch, user=None):
	if not branch:
		frappe.throw(_("branch is required"))

	from custom_erpnext.services.branch_permission_service import (
		bypass_branch_restrictions,
		user_has_branch_access,
	)

	user = user or frappe.session.user
	exists = frappe.db.exists("Company Branch", {"name": branch, "is_active": 1})

	# Privileged callers get a precise diagnostic.
	if bypass_branch_restrictions(user):
		if not exists:
			frappe.throw(_("Branch {0} not found or inactive").format(branch))
		return

	# Restricted callers get one uniform 403 whether the branch is missing,
	# inactive, or simply not assigned to them — so branch identifiers cannot be
	# enumerated by diffing "not found" against "not permitted" (SEC-10).
	if not exists or not user_has_branch_access(user, branch):
		frappe.throw(
			_("Not permitted to access branch {0}").format(branch),
			frappe.PermissionError,
		)


def validate_company(company):
	if not company:
		frappe.throw(_("company is required"))
	if not frappe.db.exists("Company", company):
		frappe.throw(_("Company {0} not found").format(company))


def get_warehouse_branch(warehouse, *, require_branch=False):
	"""Return the branch linked on a Warehouse, optionally requiring it."""
	if not warehouse:
		return None
	warehouse_branch = frappe.db.get_value("Warehouse", warehouse, "branch")
	if require_branch and not warehouse_branch:
		frappe.throw(
			_("Warehouse {0} is not linked to a branch").format(warehouse),
			frappe.ValidationError,
		)
	return warehouse_branch


def validate_warehouse_access(warehouse, user=None, *, require_branch=False):
	"""Reject access when a warehouse belongs to a branch the caller cannot access."""
	if not warehouse:
		return None

	from custom_erpnext.services.branch_permission_service import (
		bypass_branch_restrictions,
		user_has_branch_access,
	)

	user = user or frappe.session.user
	warehouse_branch = get_warehouse_branch(warehouse, require_branch=require_branch)
	if bypass_branch_restrictions(user):
		return warehouse_branch
	if warehouse_branch and not user_has_branch_access(user, warehouse_branch):
		frappe.throw(
			_("Not permitted to access warehouse {0}").format(warehouse),
			frappe.PermissionError,
		)
	return warehouse_branch


def validate_branch_warehouse_consistency(branch, warehouse):
	"""Ensure an explicit branch matches the warehouse's branch when both are sent."""
	if not branch or not warehouse:
		return
	warehouse_branch = get_warehouse_branch(warehouse, require_branch=True)
	if branch != warehouse_branch:
		frappe.throw(
			_("branch {0} does not match warehouse branch {1}").format(branch, warehouse_branch),
			frappe.ValidationError,
		)


def cint_safe(value, default=0):
	try:
		return int(value)
	except (TypeError, ValueError):
		return default
