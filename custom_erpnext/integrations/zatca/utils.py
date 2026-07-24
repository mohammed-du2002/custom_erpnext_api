# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Utilities for bridging custom_erpnext retail fields with ksa_compliance."""

from __future__ import annotations

import os
import re
import subprocess

import frappe

KSA_STATUS_TO_ZATCA_STATUS = {
	"Rejected": "Rejected",
	"Ready For Batch": "Processing",
	"Resend": "Processing",
	"Corrected": "Processing",
	"Clearance switched off": "Processing",
	"Duplicate": "Processing",
	"": "Pending",
}

KSA_INVOICE_TYPE_TO_EINVOICE = {
	"B2B - Standard": "B2B",
	"B2C - Simplified": "B2C",
	"Standard": "B2B",
	"Simplified": "B2C",
}


def is_ksa_compliance_installed():
	return "ksa_compliance" in frappe.get_installed_apps()


def extract_vat_from_certificate(cert_path: str) -> str | None:
	"""Read the Saudi VAT (UID=...) embedded in a ZATCA X.509 certificate."""
	if not cert_path or not os.path.isfile(cert_path):
		return None
	try:
		output = subprocess.check_output(
			["openssl", "x509", "-in", cert_path, "-noout", "-text"],
			text=True,
			stderr=subprocess.STDOUT,
		)
	except (FileNotFoundError, subprocess.CalledProcessError):
		return None
	match = re.search(r"UID=(\d{15})", output)
	return match.group(1) if match else None


def certificate_vat_alignment(settings) -> dict[str, str | bool | None]:
	"""Compare supplier VAT in settings with the active production certificate."""
	settings_vat = (settings.vat_registration_number or "").strip()
	cert_path = getattr(settings, "cert_path", "") or ""
	cert_vat = extract_vat_from_certificate(cert_path) if cert_path else None
	aligned = not cert_vat or settings_vat == cert_vat
	return {
		"aligned": aligned,
		"settings_vat": settings_vat or None,
		"cert_vat": cert_vat,
	}


def sync_customer_tax_ids(doc, method=None):
	"""Keep ERPNext tax_id aligned with ksa_compliance VAT field."""
	if not is_ksa_compliance_installed():
		return

	tax_id = (doc.tax_id or "").strip()
	vat = (doc.get("custom_vat_registration_number") or "").strip()

	if tax_id and not vat:
		doc.custom_vat_registration_number = tax_id
	elif vat and not tax_id:
		doc.tax_id = vat


def ensure_erpnext_branch_for_company_branch(company_branch, method=None):
	"""Create/update ERPNext Branch with the same name as Company Branch for ksa_compliance."""
	company_branch_name = company_branch if isinstance(company_branch, str) else company_branch.name
	if not company_branch_name or not is_ksa_compliance_installed():
		return None

	if not frappe.db.exists("Company Branch", company_branch_name):
		return None

	cb = frappe.get_doc("Company Branch", company_branch_name)
	branch_name = cb.name
	branch_meta = frappe.get_meta("Branch")

	if frappe.db.exists("Branch", branch_name):
		branch = frappe.get_doc("Branch", branch_name)
	else:
		branch = frappe.new_doc("Branch")
		branch.branch = branch_name

	if branch_meta.get_field("custom_company"):
		branch.custom_company = cb.company

	if (
		branch_meta.get_field("custom_company_address")
		and cb.address
		and frappe.db.exists("Address", cb.address)
	):
		branch.custom_company_address = cb.address

	_sync_branch_crn(branch, cb, branch_meta)

	branch.flags.ignore_permissions = True
	if branch.is_new():
		branch.insert(ignore_permissions=True)
	else:
		branch.save(ignore_permissions=True)

	return branch.name


def _sync_branch_crn(branch, company_branch, branch_meta=None):
	"""Populate ksa_compliance Branch.custom_branch_ids with the CRN when configured."""
	crn = (company_branch.get("commercial_registration_number") or "").strip()
	branch_meta = branch_meta or frappe.get_meta("Branch")
	if not crn or not branch_meta.get_field("custom_branch_ids"):
		return

	try:
		from ksa_compliance.ksa_compliance.doctype.zatca_business_settings.zatca_business_settings import (
			ZATCABusinessSettings,
		)

		if not ZATCABusinessSettings.is_branch_config_enabled(company_branch.company):
			return
	except Exception:
		return

	for row in branch.get("custom_branch_ids") or []:
		if (row.value or "").strip() == crn:
			return

	registration_type = frappe.db.get_value("Registration Type", {"type_code": "CRN"}, "name")
	row = {"value": crn, "type_code": "CRN"}
	if registration_type:
		row["type_name"] = registration_type
	branch.append("custom_branch_ids", row)


def persist_customer_vat(customer):
	"""Copy tax_id -> custom_vat_registration_number so ksa B2B detection works."""
	values = frappe.db.get_value(
		"Customer", customer, ["tax_id", "custom_vat_registration_number"], as_dict=True
	)
	if not values:
		return

	tax_id = (values.tax_id or "").strip()
	vat = (values.custom_vat_registration_number or "").strip()

	if tax_id and not vat:
		frappe.db.set_value(
			"Customer", customer, "custom_vat_registration_number", tax_id, update_modified=False
		)
	elif vat and not tax_id:
		frappe.db.set_value("Customer", customer, "tax_id", vat, update_modified=False)


def map_integration_status(integration_status, invoice_type=None):
	status = (integration_status or "").strip()
	if status == "Rejected":
		return "Rejected"

	if status in ("Accepted", "Accepted with warnings"):
		invoice_type = (invoice_type or "").lower()
		if "simplified" in invoice_type or "b2c" in invoice_type:
			return "Reported"
		return "Cleared"

	return KSA_STATUS_TO_ZATCA_STATUS.get(status, "Pending")


def map_zatca_sync_status(zatca_status):
	if zatca_status == "Rejected":
		return "Failed"
	if zatca_status in ("Cleared", "Reported"):
		return "Synced"
	if zatca_status == "Processing":
		return "Processing"
	return "Pending"


def map_invoice_type_to_einvoice(invoice_type):
	if not invoice_type:
		return "B2C"
	return KSA_INVOICE_TYPE_TO_EINVOICE.get(invoice_type, "B2C")


def get_latest_siaf(invoice_name, doctype="Sales Invoice"):
	if not is_ksa_compliance_installed():
		return None

	return frappe.db.get_value(
		"Sales Invoice Additional Fields",
		{"sales_invoice": invoice_name, "invoice_doctype": doctype, "is_latest": 1},
		[
			"name",
			"uuid",
			"integration_status",
			"qr_code",
			"invoice_hash",
			"invoice_type_transaction",
			"validation_errors",
			"last_attempt",
		],
		as_dict=True,
	)


def derive_invoice_type_from_siaf(siaf):
	txn = (siaf.get("invoice_type_transaction") if isinstance(siaf, dict) else siaf.invoice_type_transaction) or ""
	txn = txn.strip()
	if txn.startswith("01"):
		return "Standard"
	if txn.startswith("02"):
		return "Simplified"
	return None


def build_zatca_display_payload(siaf):
	if isinstance(siaf, str):
		siaf = frappe.get_doc("Sales Invoice Additional Fields", siaf)

	if isinstance(siaf, dict):
		integration_status = siaf.get("integration_status")
		invoice_type = derive_invoice_type_from_siaf(siaf)
		zatca_status = map_integration_status(integration_status, invoice_type)
		return {
			"siaf": siaf.get("name"),
			"zatca_reference": siaf.get("uuid") or siaf.get("name"),
			"integration_status": integration_status,
			"zatca_status": zatca_status,
			"zatca_sync_status": map_zatca_sync_status(zatca_status),
			"e_invoice_type": map_invoice_type_to_einvoice(invoice_type),
			"qr_code": siaf.get("qr_code"),
			"invoice_hash": siaf.get("invoice_hash"),
			"rejection_reason": siaf.get("validation_errors"),
			"pi_number": None,
			"last_attempt": siaf.get("last_attempt"),
		}

	integration_status = siaf.integration_status
	invoice_type = derive_invoice_type_from_siaf(siaf)
	zatca_status = map_integration_status(integration_status, invoice_type)

	return {
		"siaf": siaf.name,
		"zatca_reference": siaf.uuid or siaf.name,
		"integration_status": integration_status,
		"zatca_status": zatca_status,
		"zatca_sync_status": map_zatca_sync_status(zatca_status),
		"e_invoice_type": map_invoice_type_to_einvoice(invoice_type),
		"qr_code": siaf.qr_code,
		"invoice_hash": siaf.invoice_hash,
		"rejection_reason": getattr(siaf, "validation_errors", None),
		"pi_number": siaf.sales_invoice if hasattr(siaf, "sales_invoice") else None,
		"last_attempt": getattr(siaf, "last_attempt", None),
	}


def get_zatca_payload_for_invoice(invoice_name, doctype="Sales Invoice"):
	siaf = get_latest_siaf(invoice_name, doctype=doctype)
	if not siaf:
		return {
			"sales_invoice": invoice_name,
			"zatca_status": "Pending",
			"zatca_sync_status": "Pending",
			"zatca_reference": None,
			"e_invoice_type": None,
			"qr_code": None,
			"invoice_hash": None,
			"rejection_reason": None,
			"engine": "ksa_compliance",
		}

	payload = build_zatca_display_payload(siaf)
	payload["sales_invoice"] = invoice_name
	payload["engine"] = "ksa_compliance"
	return payload


def is_b2b_customer(customer):
	if is_ksa_compliance_installed():
		from ksa_compliance.ksa_compliance.doctype.sales_invoice_additional_fields.sales_invoice_additional_fields import (
			is_b2b_customer as ksa_is_b2b,
		)

		if isinstance(customer, str):
			customer = frappe.get_doc("Customer", customer)
		return ksa_is_b2b(customer)

	from custom_erpnext.services.sales_invoice_service import is_valid_tax_id

	if isinstance(customer, str):
		tax_id = frappe.db.get_value("Customer", customer, "tax_id")
	else:
		tax_id = customer.get("tax_id")
	return is_valid_tax_id(tax_id)


def sync_all_company_branches_to_erpnext():
	if not is_ksa_compliance_installed():
		return {"synced": 0}

	branches = frappe.get_all("Company Branch", filters={"is_active": 1}, pluck="name")
	for branch_name in branches:
		ensure_erpnext_branch_for_company_branch(branch_name)

	return {"synced": len(branches)}


def sync_all_customer_tax_ids():
	"""Bulk-align Customer tax_id / VAT fields with two UPDATEs (FC-safe)."""
	if not is_ksa_compliance_installed():
		return {"synced": 0}

	if not frappe.db.has_column("Customer", "custom_vat_registration_number"):
		return {"synced": 0}

	# Prefer set-based updates over per-row set_value to avoid connection spikes.
	to_vat = frappe.db.sql(
		"""
		SELECT COUNT(*) FROM `tabCustomer`
		WHERE IFNULL(tax_id, '') != ''
			AND IFNULL(custom_vat_registration_number, '') = ''
		"""
	)[0][0]
	if to_vat:
		frappe.db.sql(
			"""
			UPDATE `tabCustomer`
			SET custom_vat_registration_number = tax_id
			WHERE IFNULL(tax_id, '') != ''
				AND IFNULL(custom_vat_registration_number, '') = ''
			"""
		)

	to_tax = frappe.db.sql(
		"""
		SELECT COUNT(*) FROM `tabCustomer`
		WHERE IFNULL(custom_vat_registration_number, '') != ''
			AND IFNULL(tax_id, '') = ''
		"""
	)[0][0]
	if to_tax:
		frappe.db.sql(
			"""
			UPDATE `tabCustomer`
			SET tax_id = custom_vat_registration_number
			WHERE IFNULL(custom_vat_registration_number, '') != ''
				AND IFNULL(tax_id, '') = ''
			"""
		)

	return {"synced": int(to_vat) + int(to_tax)}
