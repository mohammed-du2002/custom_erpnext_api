# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import cint

from custom_erpnext.services.branch_permission_service import (
	get_default_branch,
	get_user_branches,
	user_has_branch_access,
)


@frappe.whitelist()
def get_user_discount_limits(user=None):
	"""Return discount limits for client-side validation."""
	user = user or frappe.session.user
	profile = frappe.db.get_value(
		"User Discount Profile",
		{"user": user},
		["max_discount_percent", "require_approval_above", "approval_authority", "is_branch_manager"],
		as_dict=True,
	)
	user_fields = frappe.db.get_value("User", user, ["max_discount", "branch"], as_dict=True) or {}

	max_discount = 0
	if profile and profile.max_discount_percent:
		max_discount = profile.max_discount_percent
	elif user_fields.get("max_discount"):
		max_discount = user_fields.max_discount

	return {
		"user": user,
		"max_discount_percent": max_discount,
		"require_approval_above": profile.require_approval_above if profile else 0,
		"approval_authority": profile.approval_authority if profile else 0,
		"is_branch_manager": profile.is_branch_manager if profile else 0,
		"default_branch": get_default_branch(user),
		"allowed_branches": get_user_branches(user),
	}


@frappe.whitelist()
def validate_user_branch_access(user, branch):
	"""Check if user can access a branch (for POS Profile validation)."""
	if not user or not branch:
		return {"allowed": False, "message": "User and branch are required"}

	if user_has_branch_access(user, branch):
		return {"allowed": True}

	return {
		"allowed": False,
		"message": __("User {0} is not assigned to branch {1}").format(user, branch),
	}


@frappe.whitelist()
def get_branch_naming_series(doctype, branch, is_return=0):
	from custom_erpnext.services.naming_series_service import get_naming_series_for_branch

	series = get_naming_series_for_branch(doctype, branch, is_return=cint(is_return))
	if not series:
		return {"naming_series": None, "message": _("No naming series configured for this branch")}

	return {"naming_series": series}
