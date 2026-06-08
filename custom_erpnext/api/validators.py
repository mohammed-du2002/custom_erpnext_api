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
	validate_branch(branch)

	from custom_erpnext.services.branch_permission_service import user_has_branch_access

	user = user or frappe.session.user
	if not user_has_branch_access(user, branch):
		frappe.throw(_("Not permitted to access branch {0}").format(branch))


def validate_company(company):
	if not company:
		frappe.throw(_("company is required"))
	if not frappe.db.exists("Company", company):
		frappe.throw(_("Company {0} not found").format(company))


def cint_safe(value, default=0):
	try:
		return int(value)
	except (TypeError, ValueError):
		return default
