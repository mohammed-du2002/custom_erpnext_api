# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Production readiness checks for ksa_compliance / ZATCA integration."""

from __future__ import annotations

import json
import os
from typing import Any

import frappe
from frappe.utils import now_datetime

from custom_erpnext.integrations.zatca.hooks import verify_zatca_integration
from custom_erpnext.integrations.zatca.utils import certificate_vat_alignment, is_ksa_compliance_installed


def _check(name: str, passed: bool, detail: str = "", severity: str = "error") -> dict[str, Any]:
	return {
		"name": name,
		"passed": passed,
		"detail": detail,
		"severity": severity,
	}


def _company_checks(company: str) -> list[dict[str, Any]]:
	checks: list[dict[str, Any]] = []
	if not frappe.db.exists("Company", company):
		return [_check("company_exists", False, f"Company '{company}' not found")]

	company_doc = frappe.get_doc("Company", company)
	checks.append(_check("company_country", company_doc.country == "Saudi Arabia", company_doc.country or "missing"))
	checks.append(
		_check(
			"company_vat",
			bool((company_doc.tax_id or "").strip()),
			company_doc.tax_id or "Company tax_id / VAT is empty",
		)
	)

	address_name = frappe.db.get_value(
		"Dynamic Link",
		{"link_doctype": "Company", "link_name": company, "parenttype": "Address"},
		"parent",
	)
	if not address_name:
		checks.append(_check("company_address", False, "No Address linked to company"))
		return checks

	address = frappe.get_doc("Address", address_name)
	checks.append(_check("address_country", address.country == "Saudi Arabia", address.country or "missing"))
	checks.append(
		_check(
			"address_building_number",
			bool((address.get("custom_building_number") or "").strip()),
			address.get("custom_building_number") or "custom_building_number is required",
		)
	)
	checks.append(
		_check(
			"address_area",
			bool((address.get("custom_area") or "").strip()),
			address.get("custom_area") or "custom_area (district) is required",
		)
	)
	checks.append(
		_check(
			"address_line1",
			bool((address.address_line1 or "").strip()),
			address.address_line1 or "Street address is required",
		)
	)
	return checks


def _settings_checks(company: str, target_env: str) -> list[dict[str, Any]]:
	checks: list[dict[str, Any]] = []
	settings_name = frappe.db.get_value(
		"ZATCA Business Settings",
		{"company": company, "status": "Active"},
		"name",
	)
	if not settings_name:
		return [_check("zatca_business_settings", False, "No active ZATCA Business Settings for company")]

	settings = frappe.get_doc("ZATCA Business Settings", settings_name)
	checks.append(
		_check(
			"zatca_integration_enabled",
			bool(settings.enable_zatca_integration),
			"Enable ZATCA integration on ZATCA Business Settings",
		)
	)
	checks.append(
		_check(
			"fatoora_server",
			settings.fatoora_server == target_env,
			f"Expected '{target_env}', got '{settings.fatoora_server}'",
			severity="warning" if settings.fatoora_server != target_env else "error",
		)
	)
	checks.append(
		_check(
			"seller_vat",
			bool((settings.vat_registration_number or "").strip()),
			settings.vat_registration_number or "VAT registration number missing",
		)
	)
	checks.append(
		_check(
			"company_unit",
			bool((settings.company_unit or "").strip()),
			settings.company_unit or "Company Unit (EGS name / TIN) missing",
		)
	)
	checks.append(
		_check(
			"company_unit_serial",
			bool((settings.company_unit_serial or "").strip()),
			settings.company_unit_serial or "Company Unit Serial missing",
		)
	)
	checks.append(
		_check(
			"crn_configured",
			any((row.value or "").strip() for row in settings.get("other_ids") or [] if row.type_code == "CRN"),
			"Commercial Registration Number (CRN) not set in Additional IDs",
		)
	)
	checks.append(
		_check(
			"tax_category",
			bool(settings.zatca_tax_category),
			settings.zatca_tax_category or "ZATCA tax category not configured",
		)
	)
	checks.append(
		_check(
			"sync_mode",
			bool(settings.sync_with_zatca),
			settings.sync_with_zatca or "Sync mode not configured",
			severity="warning",
		)
	)
	return checks


def _cli_and_onboarding_checks(company: str, require_production_csid: bool) -> list[dict[str, Any]]:
	checks: list[dict[str, Any]] = []
	settings_name = frappe.db.get_value(
		"ZATCA Business Settings",
		{"company": company, "status": "Active"},
		"name",
	)
	if not settings_name:
		return checks

	settings = frappe.get_doc("ZATCA Business Settings", settings_name)
	cli_path = (settings.zatca_cli_path or "").strip()
	java_home = (settings.java_home or "").strip()
	checks.append(
		_check(
			"zatca_cli_path",
			bool(cli_path and os.path.isfile(cli_path)),
			cli_path or "ZATCA CLI path not configured",
		)
	)
	checks.append(
		_check(
			"java_home",
			bool(java_home and os.path.isdir(java_home)),
			java_home or "Java home not configured",
		)
	)
	checks.append(
		_check(
			"compliance_csid",
			bool(settings.compliance_request_id),
			"Not onboarded — run Onboard to obtain Compliance CSID",
		)
	)
	checks.append(
		_check(
			"compliance_cert_file",
			bool(settings.compliance_request_id and os.path.isfile(settings.compliance_cert_path)),
			getattr(settings, "compliance_cert_path", "") or "Compliance certificate file missing",
		)
	)
	if require_production_csid:
		checks.append(
			_check(
				"production_csid",
				bool(settings.production_request_id),
				"Production CSID not obtained — required before live invoicing",
			)
		)
		checks.append(
			_check(
				"production_cert_file",
				bool(settings.production_request_id and os.path.isfile(settings.cert_path)),
				getattr(settings, "cert_path", "") or "Production certificate file missing",
			)
		)
		alignment = certificate_vat_alignment(settings)
		if alignment["cert_vat"]:
			checks.append(
				_check(
					"production_cert_vat_match",
					bool(alignment["aligned"]),
					(
						f"Supplier VAT {alignment['settings_vat']} must match production certificate VAT "
						f"{alignment['cert_vat']} (certificate-permissions)"
					),
				)
			)
	return checks


def _recent_invoice_checks(company: str) -> list[dict[str, Any]]:
	checks: list[dict[str, Any]] = []
	rejected = frappe.db.count(
		"Sales Invoice Additional Fields",
		{
			"integration_status": "Rejected",
			"is_latest": 1,
		},
	)
	checks.append(
		_check(
			"no_rejected_siaf",
			rejected == 0,
			f"{rejected} invoice(s) rejected by ZATCA",
			severity="warning",
		)
	)

	pending = frappe.db.sql(
		"""
		SELECT COUNT(*)
		FROM `tabSales Invoice Additional Fields` siaf
		INNER JOIN `tabSales Invoice` si ON si.name = siaf.sales_invoice
		WHERE siaf.is_latest = 1
		  AND si.company = %(company)s
		  AND IFNULL(siaf.integration_status, '') NOT IN ('Accepted', 'Accepted with warnings', 'REPORTED', 'CLEARED')
		""",
		{"company": company},
	)[0][0]
	checks.append(
		_check(
			"no_pending_submissions",
			pending == 0,
			f"{pending} invoice(s) not yet accepted by ZATCA",
			severity="warning",
		)
	)
	return checks


@frappe.whitelist()
def check_production_readiness(
	company: str = "tsc",
	target_env: str = "Production",
	require_production_csid: int = 1,
) -> dict[str, Any]:
	"""Return a structured readiness report for going live with ZATCA."""
	frappe.only_for("System Manager")

	report: dict[str, Any] = {
		"company": company,
		"target_env": target_env,
		"checked_at": str(now_datetime()),
		"sections": {},
	}

	integration = verify_zatca_integration()
	report["sections"]["integration"] = [
		_check("ksa_compliance_installed", integration["ksa_compliance_installed"]),
		_check("sales_invoice_fields", integration["ready"], str(integration["sales_invoice_fields"])),
		_check("legacy_doctypes_removed", integration["legacy_doctypes_removed"]),
	]

	if not is_ksa_compliance_installed():
		report["ready_for_production"] = False
		report["summary"] = {"passed": 0, "failed": 1, "warnings": 0}
		return report

	report["sections"]["company"] = _company_checks(company)
	report["sections"]["zatca_settings"] = _settings_checks(company, target_env)
	report["sections"]["cli_and_onboarding"] = _cli_and_onboarding_checks(
		company, require_production_csid=bool(require_production_csid)
	)
	report["sections"]["invoice_health"] = _recent_invoice_checks(company)

	all_checks = [row for rows in report["sections"].values() for row in rows]
	failed = [row for row in all_checks if not row["passed"] and row["severity"] == "error"]
	warnings = [row for row in all_checks if not row["passed"] and row["severity"] == "warning"]

	report["summary"] = {
		"passed": sum(1 for row in all_checks if row["passed"]),
		"failed": len(failed),
		"warnings": len(warnings),
	}
	report["blocking_issues"] = [row["name"] for row in failed]
	report["warnings"] = [row["name"] for row in warnings]
	report["ready_for_production"] = len(failed) == 0
	return report


@frappe.whitelist()
def check_sandbox_readiness(company: str = "tsc") -> dict[str, Any]:
	"""Readiness focused on Sandbox testing (before Simulation/Production)."""
	report = check_production_readiness(
		company=company,
		target_env="Sandbox",
		require_production_csid=0,
	)
	report["ready_for_sandbox_testing"] = report.pop("ready_for_production")
	return report


def main(company: str = "tsc", mode: str = "production") -> None:
	"""Entry point: bench execute custom_erpnext.integrations.zatca.production_readiness.main"""
	frappe.set_user("Administrator")
	if mode == "sandbox":
		result = check_sandbox_readiness(company=company)
	else:
		result = check_production_readiness(company=company)
	print(json.dumps(result, indent=2, default=str))
