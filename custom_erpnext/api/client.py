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
		"message": _("User {0} is not assigned to branch {1}").format(user, branch),
	}


@frappe.whitelist()
def get_customer_einvoice_type(customer):
	"""Authoritative B2B/B2C classification for desk + POS, matching the server.

	Uses ksa_compliance.is_b2b_customer when installed (VAT number OR any
	additional buyer ID), falling back to a 15-digit tax_id check otherwise.
	"""
	if not customer:
		return {"e_invoice_type": "B2C", "is_b2b": False}

	from custom_erpnext.integrations.zatca.utils import is_b2b_customer

	is_b2b = bool(is_b2b_customer(customer))
	tax_id = (
		frappe.db.get_value("Customer", customer, "custom_vat_registration_number")
		or frappe.db.get_value("Customer", customer, "tax_id")
		or ""
	)
	return {
		"e_invoice_type": "B2B" if is_b2b else "B2C",
		"is_b2b": is_b2b,
		"tax_id": (tax_id or "").strip(),
	}


@frappe.whitelist()
def get_branch_naming_series(doctype, branch, is_return=0):
	from custom_erpnext.services.naming_series_service import get_naming_series_for_branch

	series = get_naming_series_for_branch(doctype, branch, is_return=cint(is_return))
	if not series:
		return {"naming_series": None, "message": _("No naming series configured for this branch")}

	return {"naming_series": series}


@frappe.whitelist()
def validate_zatca_customer_address(customer_address=None, customer=None):
	"""Validate buyer address for ZATCA e-invoicing (desk pre-check)."""
	from custom_erpnext.services.address_validation_service import validate_zatca_customer_address

	if not customer_address and customer:
		from frappe.contacts.doctype.address.address import get_default_address

		customer_address = get_default_address("Customer", customer)

	if customer_address and not frappe.has_permission("Address", "read", customer_address):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	return validate_zatca_customer_address(customer_address)


@frappe.whitelist()
def get_sales_invoice_zatca_status(sales_invoice=None, offline_invoice_id=None):
	"""Return ZATCA payload mirrored from ksa_compliance for desk/Laravel polling."""
	from custom_erpnext.integrations.zatca.utils import get_zatca_payload_for_invoice

	if not sales_invoice and offline_invoice_id:
		from custom_erpnext.services.sales_invoice_sync_service import find_invoice_by_sync_key

		sales_invoice = find_invoice_by_sync_key(offline_invoice_id)

	if not sales_invoice:
		frappe.throw(_("sales_invoice or offline_invoice_id is required"))

	if not frappe.has_permission("Sales Invoice", "read", sales_invoice):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	return get_zatca_payload_for_invoice(sales_invoice)
