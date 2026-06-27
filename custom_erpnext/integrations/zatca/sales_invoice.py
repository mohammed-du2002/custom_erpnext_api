# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Sales Invoice integration with ksa_compliance for ZATCA e-invoicing."""

import frappe
from frappe.utils import cint

from custom_erpnext.integrations.zatca.utils import (
	build_zatca_display_payload,
	ensure_erpnext_branch_for_company_branch,
	is_ksa_compliance_installed,
	persist_customer_vat,
)


def prepare_sales_invoice_for_zatca(doc, method=None):
	"""Ensure customer VAT and ERPNext Branch exist before ksa_compliance hooks run."""
	if not is_ksa_compliance_installed() or not doc.get("branch"):
		return

	if doc.customer:
		persist_customer_vat(doc.customer)

	ensure_erpnext_branch_for_company_branch(doc.branch)


def submit_zatca(doc, method=None):
	"""Mark retail ZATCA fields and delegate submission to ksa_compliance.

	ksa_compliance registers its own ``on_submit`` hook that creates
	``Sales Invoice Additional Fields`` and enqueues ZATCA submission.
	This handler only prepares retail-side tracking fields.
	"""
	if not is_ksa_compliance_installed():
		return

	if not cint(doc.get("is_e_invoice")):
		return

	prepare_sales_invoice_for_zatca(doc)

	frappe.db.set_value(
		"Sales Invoice",
		doc.name,
		{
			"zatca_status": "Processing",
			"zatca_sync_status": "Processing",
		},
		update_modified=False,
	)


def mirror_siaf_to_sales_invoice(doc, method=None):
	"""Mirror ksa_compliance submission results to retail Sales Invoice fields."""
	if not is_ksa_compliance_installed():
		return

	if doc.invoice_doctype not in ("Sales Invoice", "POS Invoice"):
		return

	invoice_name = doc.sales_invoice
	if not invoice_name or doc.invoice_doctype != "Sales Invoice":
		return

	if not frappe.db.exists("Sales Invoice", invoice_name):
		return

	payload = build_zatca_display_payload(doc)
	frappe.db.set_value(
		"Sales Invoice",
		invoice_name,
		{
			"zatca_reference": payload.get("zatca_reference"),
			"zatca_status": payload.get("zatca_status"),
			"zatca_sync_status": payload.get("zatca_sync_status"),
			"e_invoice_type": payload.get("e_invoice_type"),
			"is_e_invoice": 1,
			"pi_number": payload.get("pi_number") or invoice_name,
		},
		update_modified=False,
	)
