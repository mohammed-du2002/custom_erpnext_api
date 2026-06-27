# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""ZATCA Sandbox setup and smoke test for ksa_compliance on a Frappe site."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from typing import Any

import frappe
from frappe.utils import now_datetime
from result import is_ok

from custom_erpnext.integrations.zatca.utils import (
	certificate_vat_alignment,
	extract_vat_from_certificate,
	is_ksa_compliance_installed,
)

SANDBOX_OTP = "123345"
SANDBOX_VAT = "311111111111003"
SANDBOX_CRN = "1010123456"
# When the 11th digit of the sandbox VAT is 1, ZATCA requires a 10-digit TIN in Organization Unit Name.
SANDBOX_TIN = SANDBOX_VAT[1:11]
DEFAULT_COMPANY = "tsc"
DEFAULT_ITEM = "ZATCA-TEST-SERVICE"
FALLBACK_ITEM = "RET-TRASH-BAG"
SIMPLIFIED_CUSTOMER = "ZATCA Sandbox B2C"
STANDARD_CUSTOMER = "ZATCA Sandbox B2B"
ADDRESS_TITLE = "TSC ZATCA Sandbox"


def _require_ksa_compliance() -> None:
	if not is_ksa_compliance_installed():
		frappe.throw("ksa_compliance is not installed on this site.")


def _log(step: str, detail: str = "") -> None:
	message = f"[ZATCA Sandbox] {step}"
	if detail:
		message = f"{message}: {detail}"
	frappe.logger("zatca_sandbox").info(message)
	print(message)


def ensure_company_address(company: str = DEFAULT_COMPANY) -> str:
	existing = frappe.db.get_value(
		"Address",
		{"address_title": ADDRESS_TITLE, "country": "Saudi Arabia"},
		"name",
	)
	if existing:
		return existing

	address = frappe.new_doc("Address")
	address.address_title = ADDRESS_TITLE
	address.address_type = "Office"
	address.address_line1 = "King Fahd Road"
	address.city = "Riyadh"
	address.pincode = "12345"
	address.country = "Saudi Arabia"
	address.custom_building_number = "1234"
	address.custom_area = "Al Olaya"
	address.append("links", {"link_doctype": "Company", "link_name": company})
	address.insert(ignore_permissions=True)
	return address.name


def _ensure_customer_address(customer_name: str, company: str = DEFAULT_COMPANY) -> str:
	title = f"{customer_name} Address"
	existing = frappe.db.get_value(
		"Address",
		{"address_title": title, "country": "Saudi Arabia"},
		"name",
	)
	if existing:
		return existing

	address = frappe.new_doc("Address")
	address.address_title = title
	address.address_type = "Billing"
	address.address_line1 = "King Fahd Road"
	address.city = "Riyadh"
	address.pincode = "12345"
	address.country = "Saudi Arabia"
	address.custom_building_number = "5678"
	address.custom_area = "Al Olaya"
	address.append("links", {"link_doctype": "Customer", "link_name": customer_name})
	address.insert(ignore_permissions=True)
	return address.name


def ensure_test_customers() -> dict[str, str]:
	simplified = _ensure_customer(
		SIMPLIFIED_CUSTOMER,
		customer_type="Individual",
		customer_group="Individual",
		vat=None,
	)
	standard = _ensure_customer(
		STANDARD_CUSTOMER,
		customer_type="Company",
		customer_group="Commercial",
		vat="310122333444003",
	)
	_ensure_customer_address(standard)
	frappe.db.set_value("Customer", standard, "customer_primary_address", _ensure_customer_address(standard), update_modified=False)
	return {"simplified": simplified, "standard": standard}


def _ensure_customer(
	name: str,
	customer_type: str,
	customer_group: str,
	vat: str | None,
) -> str:
	if frappe.db.exists("Customer", name):
		customer = frappe.get_doc("Customer", name)
	else:
		customer = frappe.new_doc("Customer")
		customer.customer_name = name
		customer.customer_type = customer_type
		customer.customer_group = customer_group
		customer.territory = frappe.db.get_value("Territory", {"is_group": 0}, "name") or "Rest Of The World"
		customer.insert(ignore_permissions=True)

	if vat:
		frappe.db.set_value("Customer", customer.name, "custom_vat_registration_number", vat, update_modified=False)
		frappe.db.set_value("Customer", customer.name, "tax_id", vat, update_modified=False)
	else:
		frappe.db.set_value("Customer", customer.name, "custom_vat_registration_number", "", update_modified=False)
		frappe.db.set_value("Customer", customer.name, "tax_id", "", update_modified=False)

	return customer.name


def _sandbox_company_unit(vat: str = SANDBOX_VAT) -> str:
	"""Return Organization Unit Name valid for ZATCA CSR (10-digit TIN when VAT 11th digit is 1)."""
	if len(vat) == 15 and vat[10] == "1":
		return vat[1:11]
	return ADDRESS_TITLE


def sync_sandbox_supplier_vat_with_production_cert(settings_id: str) -> dict[str, Any]:
	"""Align supplier VAT with the Sandbox production CSID certificate.

	In ZATCA Sandbox, compliance onboarding uses VAT 311111111111003, but the issued
	production CSID is bound to a fixed certificate VAT (typically 399999999900003).
	Live reporting/clearance rejects invoices when XML supplier VAT != certificate VAT.
	"""
	_require_ksa_compliance()
	settings = frappe.get_doc("ZATCA Business Settings", settings_id)
	if settings.fatoora_server != "Sandbox":
		frappe.throw("Supplier VAT sync is only applicable to Sandbox ZATCA Business Settings.")

	if not settings.production_request_id or not os.path.isfile(settings.cert_path):
		frappe.throw("Obtain Production CSID before syncing sandbox supplier VAT.")

	cert_vat = extract_vat_from_certificate(settings.cert_path)
	if not cert_vat:
		frappe.throw(f"Could not read VAT from production certificate: {settings.cert_path}")

	settings_vat = (settings.vat_registration_number or "").strip()
	if settings_vat == cert_vat:
		return {"status": "already_aligned", "vat": cert_vat}

	settings.vat_registration_number = cert_vat
	settings.company_unit = _sandbox_company_unit(cert_vat)
	settings.save(ignore_permissions=True)
	frappe.db.set_value("Company", settings.company, "tax_id", cert_vat, update_modified=False)
	frappe.db.commit()
	_log("synced_sandbox_supplier_vat", f"{settings_vat} -> {cert_vat}")
	return {"status": "synced", "previous_vat": settings_vat, "vat": cert_vat}


def diagnose_certificate_vat_mismatch(settings_id: str) -> dict[str, Any]:
	"""Return VAT alignment details for troubleshooting certificate-permissions errors."""
	_require_ksa_compliance()
	settings = frappe.get_doc("ZATCA Business Settings", settings_id)
	alignment = certificate_vat_alignment(settings)
	compliance_vat = extract_vat_from_certificate(settings.compliance_cert_path)
	return {
		"company": settings.company,
		"fatoora_server": settings.fatoora_server,
		"settings_vat": alignment["settings_vat"],
		"compliance_cert_vat": compliance_vat,
		"production_cert_vat": alignment["cert_vat"],
		"aligned": alignment["aligned"],
		"fix": (
			"Run sync_sandbox_supplier_vat_with_production_cert() for Sandbox, "
			"or re-issue CSID with the correct VAT for Simulation/Production."
		),
	}


def ensure_zatca_business_settings(company: str = DEFAULT_COMPANY) -> str:
	from ksa_compliance.ksa_compliance.doctype.zatca_business_settings.zatca_business_settings import (
		ZATCABusinessSettings,
	)

	existing_id = frappe.db.get_value(
		"ZATCA Business Settings",
		{"company": company, "status": "Active", "fatoora_server": "Sandbox"},
		"name",
	)
	address_name = ensure_company_address(company)
	company_doc = frappe.get_doc("Company", company)
	frappe.db.set_value("Company", company, "tax_id", SANDBOX_VAT, update_modified=False)
	expected_unit = _sandbox_company_unit()

	if existing_id:
		settings = frappe.get_doc("ZATCA Business Settings", existing_id)
		changed = False
		for field, value in (
			("company_address", address_name),
			("vat_registration_number", SANDBOX_VAT),
			("company_unit", expected_unit),
			("company_unit_serial", f"1-ERPNext|2-16|3-{company.upper()}-SANDBOX-001"),
			("enable_zatca_integration", 1),
			("sync_with_zatca", "Live"),
			("fatoora_server", "Sandbox"),
			("cli_setup", "Automatic"),
			("validate_generated_xml", 1),
		):
			if settings.get(field) != value:
				settings.set(field, value)
				changed = True
		if changed:
			settings.save(ignore_permissions=True)
			frappe.db.commit()
		return existing_id

	settings = frappe.new_doc("ZATCA Business Settings")
	settings.company = company
	settings.company_address = address_name
	settings.currency = company_doc.default_currency or "SAR"
	settings.seller_name = company_doc.company_name or company
	settings.vat_registration_number = SANDBOX_VAT
	settings.company_unit = expected_unit
	settings.company_unit_serial = f"1-ERPNext|2-16|3-{company.upper()}-SANDBOX-001"
	settings.company_category = "Retail"
	settings.enable_zatca_integration = 1
	settings.sync_with_zatca = "Live"
	settings.type_of_business_transactions = "Let the system decide (both)"
	settings.fatoora_server = "Sandbox"
	settings.cli_setup = "Automatic"
	settings.validate_generated_xml = 1
	settings.automatic_vat_account_configuration = 1
	settings.account_name = "VAT"
	settings.account_number = "2301"
	settings.tax_rate = 15
	settings.zatca_tax_category = "Standard rate"

	settings.append(
		"other_ids",
		{
			"type_name": "Commercial Registration Number",
			"type_code": "CRN",
			"value": SANDBOX_CRN,
		},
	)
	for row in (
		("MOMRAH License", "MOM"),
		("MHRSD License", "MLS"),
		("700 Number", "700"),
		("MISA License", "SAG"),
		("Other ID", "OTH"),
	):
		settings.append("other_ids", {"type_name": row[0], "type_code": row[1], "value": ""})

	settings.insert(ignore_permissions=True)
	return settings.name


def _download_file(url: str, target_path: str, retries: int = 5) -> None:
	"""Download a file with curl retries (more reliable than in-process streaming)."""
	os.makedirs(os.path.dirname(target_path), exist_ok=True)
	if os.path.isfile(target_path):
		os.remove(target_path)

	cmd = [
		"curl",
		"-fL",
		"--retry",
		str(retries),
		"--retry-delay",
		"5",
		"--retry-all-errors",
		"-o",
		target_path,
		url,
	]
	_log("downloading", f"{url} -> {target_path}")
	result = subprocess.run(cmd, capture_output=True, text=True, check=False)
	if result.returncode != 0:
		frappe.throw(f"Failed to download {url}: {result.stderr or result.stdout}")


def setup_zatca_cli(settings_id: str) -> dict[str, str]:
	from ksa_compliance import zatca_cli
	from ksa_compliance.zatca_cli import DEFAULT_CLI_URL, DEFAULT_JRE_URL
	from ksa_compliance.zatca_cli_setup import extract_archive
	from ksa_compliance.zatca_files import get_zatca_tool_path
	from result import is_err

	settings = frappe.get_doc("ZATCA Business Settings", settings_id)
	if settings.zatca_cli_path and settings.java_home:
		if os.path.isfile(settings.zatca_cli_path):
			return {"cli_path": settings.zatca_cli_path, "jre_path": settings.java_home}

	directory = get_zatca_tool_path()
	os.makedirs(directory, exist_ok=True)

	jre_archive = os.path.join(directory, "OpenJDK11U-jre_x64_linux_hotspot_11.0.23_9.tar.gz")
	cli_archive = os.path.join(directory, "zatca-cli-2.10.0.zip")

	_download_file(DEFAULT_JRE_URL, jre_archive)
	java_result = extract_archive(jre_archive)
	if is_err(java_result):
		frappe.throw(java_result.err_value)
	java_home = os.path.abspath(java_result.ok_value)

	_download_file(DEFAULT_CLI_URL, cli_archive)
	cli_result = extract_archive(cli_archive)
	if is_err(cli_result):
		frappe.throw(cli_result.err_value)

	cli_bin = os.path.join(os.path.abspath(cli_result.ok_value), "bin/zatca-cli")
	if not os.path.isfile(cli_bin):
		frappe.throw(f"ZATCA CLI binary not found at {cli_bin}")

	os.chmod(cli_bin, os.stat(cli_bin).st_mode | stat.S_IEXEC)

	settings.zatca_cli_path = cli_bin
	settings.java_home = java_home
	settings.save(ignore_permissions=True)
	frappe.db.commit()
	return {"cli_path": cli_bin, "jre_path": java_home}


def onboard_sandbox(settings_id: str, otp: str = SANDBOX_OTP) -> dict[str, Any]:
	from ksa_compliance.ksa_compliance.doctype.zatca_business_settings.zatca_business_settings import (
		ZATCABusinessSettings,
	)

	settings = frappe.get_doc("ZATCA Business Settings", settings_id)
	if settings.compliance_request_id:
		return {
			"status": "already_onboarded",
			"compliance_request_id": settings.compliance_request_id,
		}

	settings.onboard(otp)
	frappe.db.commit()
	settings.reload()
	return {
		"status": "onboarded",
		"compliance_request_id": settings.compliance_request_id,
	}


def ensure_test_item(item_id: str = DEFAULT_ITEM, company: str = DEFAULT_COMPANY) -> str:
	"""Use a non-stock service item so compliance tests do not require inventory."""
	if frappe.db.exists("Item", item_id):
		# If item exists but is a stock item, make it non-stock so no inventory is required
		is_stock = frappe.db.get_value("Item", item_id, "is_stock_item")
		if is_stock:
			frappe.db.set_value("Item", item_id, "is_stock_item", 0, update_modified=False)
			frappe.db.commit()
		return item_id

	item = frappe.new_doc("Item")
	item.item_code = item_id
	item.item_name = "ZATCA Test Service"
	item.item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name") or "Products"
	item.stock_uom = "Nos"
	item.is_stock_item = 0
	item.is_sales_item = 1
	item.insert(ignore_permissions=True)
	ensure_item_tax_template(item_id, company)
	frappe.db.commit()
	return item_id


def ensure_item_tax_template(item_id: str = DEFAULT_ITEM, company: str = DEFAULT_COMPANY) -> str | None:
	"""Link test item to the VAT Item Tax Template created by ZATCA Business Settings."""
	template_name = frappe.db.get_value(
		"Item Tax Template", {"company": company, "name": "VAT - 15% - T"}, "name"
	)
	if not template_name:
		return None

	existing = frappe.db.get_value("Item Tax", {"parent": item_id, "item_tax_template": template_name}, "name")
	if not existing:
		frappe.get_doc(
			{
				"doctype": "Item Tax",
				"parent": item_id,
				"parenttype": "Item",
				"parentfield": "taxes",
				"item_tax_template": template_name,
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()

	return template_name


def _make_test_invoice(company: str, customer: str, item_id: str, tax_category_id: str):
	"""Create a Sales Invoice with taxes applied (ksa_compliance _make_invoice calls set_taxes too early)."""
	tax_template = frappe.db.get_value(
		"Sales Taxes and Charges Template",
		{"company": company, "tax_category": tax_category_id},
		"name",
	)
	if not tax_template:
		frappe.throw(f"No Sales Taxes and Charges Template for tax category '{tax_category_id}'.")

	invoice = frappe.new_doc("Sales Invoice")
	invoice.company = company
	invoice.customer = customer
	invoice.tax_category = tax_category_id
	invoice.taxes_and_charges = tax_template
	if customer == STANDARD_CUSTOMER:
		address = frappe.db.get_value("Customer", customer, "customer_primary_address")
		if address:
			invoice.customer_address = address
	if frappe.get_meta("Sales Invoice").has_field("branch") and not invoice.get("branch"):
		branch = frappe.db.get_value("Company Branch", {"company": company, "is_active": 1}, "name")
		if branch:
			invoice.branch = branch
	invoice.append("items", {"item_code": item_id, "qty": 1.0})
	invoice.set_missing_values()
	invoice.set_taxes()
	if not invoice.taxes:
		frappe.throw(f"Test invoice has no taxes. Check template '{tax_template}'.")
	invoice.save()
	return invoice


def _is_compliance_passed(status: str | None, details: str | None) -> bool:
	"""Check if a ZATCA compliance result is passing.

	ksa_compliance returns verbose messages like:
	  'Invoice sent to ZATCA. Integration status: Accepted'
	The details JSON contains reportingStatus / clearanceStatus.
	"""
	if not status:
		return False
	# Check the human-readable status string for accepted keywords
	status_lower = status.lower()
	if any(k in status_lower for k in ("accepted", "reported", "cleared")):
		return True
	# Fallback: parse the details JSON for ZATCA statuses
	if details:
		try:
			parsed = json.loads(details)
			reporting = (parsed.get("reportingStatus") or "").upper()
			clearance = (parsed.get("clearanceStatus") or "").upper()
			if reporting in ("REPORTED",) or clearance in ("CLEARED",):
				return True
		except Exception:
			pass
	return False


def run_compliance_smoke_test(
	settings_id: str,
	item_id: str = DEFAULT_ITEM,
	simplified_customer: str = SIMPLIFIED_CUSTOMER,
	standard_customer: str = STANDARD_CUSTOMER,
) -> dict[str, Any]:
	from ksa_compliance.compliance_checks import _check_invoice_compliance
	from ksa_compliance.ksa_compliance.doctype.zatca_business_settings.zatca_business_settings import (
		ZATCABusinessSettings,
	)
	from ksa_compliance.standard_doctypes.sales_invoice import (
		clear_additional_fields_ignore_list,
		ignore_additional_fields_for_invoice,
	)

	settings = frappe.get_doc("ZATCA Business Settings", settings_id)
	if not settings.compliance_request_id:
		frappe.throw("Sandbox onboarding is incomplete. Run onboard first.")

	tax_category_id = frappe.db.get_value("Tax Category", {"title": "Standard rate"}, "name")
	if not tax_category_id:
		frappe.throw("Tax Category 'Standard rate' was not created by ZATCA Business Settings.")

	ensure_test_item(item_id, settings.company)
	ensure_item_tax_template(item_id, settings.company)

	results: dict[str, Any] = {}
	try:
		for label, customer in (("simplified", simplified_customer), ("standard", standard_customer)):
			invoice = _make_test_invoice(settings.company, customer, item_id, tax_category_id)
			ignore_additional_fields_for_invoice(invoice.name)
			invoice.submit()
			status, details = _check_invoice_compliance(invoice)
			results[label] = {
				"invoice": invoice.name,
				"status": status,
				"details": details,
				"passed": _is_compliance_passed(status, details),
			}
	finally:
		clear_additional_fields_ignore_list()
		frappe.db.rollback()

	return results


def verify_zatca_cli(settings_id: str) -> str:
	from ksa_compliance import zatca_cli

	settings = frappe.get_doc("ZATCA Business Settings", settings_id)
	result = zatca_cli.run_command(settings.zatca_cli_path, ["-v"], java_home=settings.java_home)
	if result.is_failure:
		frappe.throw(result.msg)
	return result.msg


@frappe.whitelist()
def setup_zatca_sandbox(company: str = DEFAULT_COMPANY, skip_cli: int = 0, skip_onboard: int = 0) -> dict[str, Any]:
	"""Create sandbox master data, CLI, and onboarding for ksa_compliance."""
	_require_ksa_compliance()
	frappe.only_for("System Manager")

	report: dict[str, Any] = {"company": company, "steps": [], "started_at": str(now_datetime())}

	customers = ensure_test_customers()
	report["customers"] = customers
	report["steps"].append("customers_ready")
	frappe.db.commit()

	settings_id = ensure_zatca_business_settings(company)
	report["business_settings"] = settings_id
	report["steps"].append("business_settings_ready")
	frappe.db.commit()

	if not skip_cli:
		cli_info = setup_zatca_cli(settings_id)
		report["cli"] = cli_info
		report["cli_version"] = verify_zatca_cli(settings_id)
		report["steps"].append("cli_ready")

	if not skip_onboard:
		report["onboarding"] = onboard_sandbox(settings_id)
		report["steps"].append("onboarded")

	report["finished_at"] = str(now_datetime())
	return report


@frappe.whitelist()
def run_zatca_sandbox_test(
	company: str = DEFAULT_COMPANY,
	item_id: str = DEFAULT_ITEM,
	run_setup: int = 1,
) -> dict[str, Any]:
	"""End-to-end ZATCA sandbox smoke test (setup + one simplified + one standard invoice)."""
	_require_ksa_compliance()
	frappe.only_for("System Manager")

	report: dict[str, Any] = {"company": company, "started_at": str(now_datetime())}
	if run_setup:
		report["setup"] = setup_zatca_sandbox(company=company)

	settings_id = frappe.db.get_value(
		"ZATCA Business Settings",
		{"company": company, "status": "Active", "fatoora_server": "Sandbox"},
		"name",
	)
	if not settings_id:
		frappe.throw("No active Sandbox ZATCA Business Settings found for this company.")

	report["compliance_checks"] = run_compliance_smoke_test(settings_id, item_id=item_id)
	report["success"] = all(row.get("passed") for row in report["compliance_checks"].values())
	report["finished_at"] = str(now_datetime())
	return report


def main(company: str = DEFAULT_COMPANY, item_id: str = DEFAULT_ITEM) -> None:
	"""Entry point for `bench execute custom_erpnext.integrations.zatca.sandbox_setup.main`."""
	frappe.set_user("Administrator")
	result = run_zatca_sandbox_test(company=company, item_id=item_id, run_setup=1)
	print(json.dumps(result, indent=2, default=str))
