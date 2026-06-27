# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Post-migrate setup for the ksa_compliance ZATCA integration."""

import frappe

from custom_erpnext.integrations.zatca.utils import (
	is_ksa_compliance_installed,
	sync_all_company_branches_to_erpnext,
	sync_all_customer_tax_ids,
)


def check_ksa_compliance_dependency():
	"""Log a clear warning when ksa_compliance is missing (does not block migrate)."""
	if is_ksa_compliance_installed():
		return {"installed": True, "message": "ksa_compliance is installed"}

	message = (
		"ksa_compliance is not installed. Saudi e-invoicing (ZATCA) is inactive; "
		"install ksa_compliance and run bench migrate to enable Sales Invoice submission to ZATCA."
	)
	frappe.logger("custom_erpnext").warning(message)
	return {"installed": False, "message": message}


def setup_zatca_integration():
	"""Run after migrate when ksa_compliance is installed."""
	if not is_ksa_compliance_installed():
		return

	_migrate_zatca_uuid_to_reference()
	branch_result = sync_all_company_branches_to_erpnext()
	customer_result = sync_all_customer_tax_ids()
	frappe.logger("custom_erpnext").info(
		"ZATCA integration setup: branches=%s customers=%s",
		branch_result.get("synced"),
		customer_result.get("synced"),
	)


def verify_zatca_integration():
	"""Return integration health for desk checks and automated tests."""
	result = {
		"ksa_compliance_installed": is_ksa_compliance_installed(),
		"sales_invoice_fields": {},
		"legacy_doctypes_removed": True,
		"hooks_registered": True,
	}

	for fieldname in (
		"is_e_invoice",
		"e_invoice_type",
		"zatca_status",
		"zatca_reference",
		"zatca_sync_status",
		"is_pos_transaction",
	):
		result["sales_invoice_fields"][fieldname] = frappe.get_meta("Sales Invoice").has_field(fieldname)

	for doctype in ("ZATCA Invoice", "ZATCA Configuration"):
		if frappe.db.exists("DocType", doctype):
			result["legacy_doctypes_removed"] = False

	result["ready"] = (
		result["ksa_compliance_installed"]
		and all(result["sales_invoice_fields"].values())
		and result["legacy_doctypes_removed"]
	)
	return result


def _migrate_zatca_uuid_to_reference():
	"""Copy legacy zatca_uuid values once new columns exist after fixture sync."""
	if not (
		frappe.db.has_column("Sales Invoice", "zatca_uuid")
		and frappe.db.has_column("Sales Invoice", "zatca_reference")
	):
		return

	frappe.db.sql(
		"""
		UPDATE `tabSales Invoice`
		SET zatca_reference = COALESCE(NULLIF(zatca_reference, ''), zatca_uuid)
		WHERE IFNULL(zatca_uuid, '') != '' AND IFNULL(zatca_reference, '') = ''
		"""
	)
