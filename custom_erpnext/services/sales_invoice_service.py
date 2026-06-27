# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import cint


def validate_sales_invoice(doc, method=None):
	from custom_erpnext.integrations.zatca.sales_invoice import prepare_sales_invoice_for_zatca
	from custom_erpnext.integrations.zatca.utils import is_ksa_compliance_installed

	if is_ksa_compliance_installed():
		prepare_sales_invoice_for_zatca(doc, method)

	apply_retail_branch_defaults(doc)
	apply_pos_transaction_flag(doc)
	apply_e_invoice_classification(doc)
	validate_b2b_requires_online(doc)
	sync_retail_customer_number(doc)
	force_update_stock_and_rounding(doc)
	validate_naming_series(doc)
	validate_customer_address_for_b2b(doc)
	validate_warehouse_branch(doc)

	from custom_erpnext.services.item_service import explode_composite_items

	explode_composite_items(doc)


def apply_retail_branch_defaults(doc):
	"""Set cost_center from Company Branch when missing (desk and API paths)."""
	if not doc.branch or doc.cost_center:
		return

	cost_center = frappe.db.get_value("Company Branch", doc.branch, "cost_center")
	if cost_center:
		doc.cost_center = cost_center


def apply_pos_transaction_flag(doc):
	"""Mark POS-originated invoices for Laravel/reporting filters."""
	if cint(doc.get("is_pos_transaction")):
		return

	if doc.get("offline_invoice_id") or doc.get("pos_device") or cint(doc.get("is_pos")):
		doc.is_pos_transaction = 1


def sync_retail_customer_number(doc):
	if doc.customer:
		doc.retail_customer_number = doc.customer


def apply_e_invoice_classification(doc):
	doc.is_e_invoice = 1

	if not doc.customer:
		doc.e_invoice_type = "B2C"
		return

	from custom_erpnext.integrations.zatca.utils import is_b2b_customer, is_ksa_compliance_installed

	if is_ksa_compliance_installed():
		doc.e_invoice_type = "B2B" if is_b2b_customer(doc.customer) else "B2C"
		tax_id = (
			frappe.db.get_value("Customer", doc.customer, "custom_vat_registration_number")
			or frappe.db.get_value("Customer", doc.customer, "tax_id")
			or doc.tax_id
			or ""
		).strip()
	else:
		tax_id = (frappe.db.get_value("Customer", doc.customer, "tax_id") or doc.tax_id or "").strip()
		doc.e_invoice_type = "B2B" if is_valid_tax_id(tax_id) else "B2C"

	if tax_id and not doc.tax_id:
		doc.tax_id = tax_id


def validate_b2b_requires_online(doc):
	"""SRS §7.3: B2B e-invoices must be issued online.

	The offline-first POS may only issue B2C (simplified) invoices while
	disconnected. A B2B invoice that originated offline (it carries an
	``offline_invoice_id``) means it was created without the mandatory online
	clearance, so it is rejected on sync.
	"""
	if doc.get("e_invoice_type") != "B2B":
		return

	if doc.get("offline_invoice_id"):
		frappe.throw(
			_(
				"B2B e-invoices require an online connection and cannot be issued "
				"from the offline POS (offline_invoice_id={0})."
			).format(doc.get("offline_invoice_id"))
		)


def force_update_stock_and_rounding(doc):
	doc.update_stock = 1
	doc.disable_rounded_total = 1


def validate_naming_series(doc):
	if not doc.branch or not doc.meta.get_field("naming_series"):
		return

	from custom_erpnext.services.naming_series_service import get_naming_series_for_branch

	expected = get_naming_series_for_branch(
		"Sales Invoice", doc.branch, is_return=cint(doc.is_return)
	)
	if not expected:
		return

	if doc.naming_series != expected:
		if doc.is_new():
			doc.naming_series = expected
		else:
			frappe.throw(
				_("Naming Series must match branch configuration: {0}").format(expected)
			)


def validate_customer_address_for_b2b(doc):
	if not doc.customer:
		return

	from custom_erpnext.integrations.zatca.utils import is_b2b_customer, is_ksa_compliance_installed
	from custom_erpnext.services.address_validation_service import throw_if_invalid_zatca_address

	if not is_b2b_customer(doc.customer):
		return

	if not doc.customer_address:
		frappe.throw(_("Customer Address is mandatory for B2B customers with Tax Number"))

	if is_ksa_compliance_installed():
		throw_if_invalid_zatca_address(doc.customer_address)


def validate_warehouse_branch(doc):
	if not doc.branch or not doc.set_warehouse:
		return

	wh_branch = frappe.db.get_value("Warehouse", doc.set_warehouse, "branch")
	if wh_branch and wh_branch != doc.branch:
		frappe.throw(
			_("Warehouse {0} does not belong to branch {1}").format(
				doc.set_warehouse, doc.branch
			)
		)


def validate_customer_tax_id(doc, method=None):
	from custom_erpnext.integrations.zatca.utils import sync_customer_tax_ids

	sync_customer_tax_ids(doc, method)

	if not doc.tax_id:
		return

	tax_id = doc.tax_id.strip()
	if not (tax_id.isdigit() and len(tax_id) == 15):
		frappe.throw(_("Tax Number must be exactly 15 digits"))


def is_valid_tax_id(tax_id):
	tax_id = (tax_id or "").strip()
	return bool(tax_id and tax_id.isdigit() and len(tax_id) == 15)
