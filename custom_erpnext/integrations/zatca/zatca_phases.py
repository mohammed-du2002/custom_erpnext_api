# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""
ZATCA phased testing: Sandbox → Simulation → Production.

Phase 1 (Sandbox)   — fully automated; dummy VAT + OTP 123345
Phase 2 (Simulation) — real VAT; OTP from https://simulation.zatca.gov.sa
Phase 3 (Production) — real VAT; OTP from https://fatoora.zatca.gov.sa
"""

from __future__ import annotations

import json
from typing import Any, Literal

import frappe
from frappe.utils import now_datetime

from custom_erpnext.integrations.zatca.production_readiness import check_production_readiness
from custom_erpnext.integrations.zatca.sandbox_setup import (
	DEFAULT_COMPANY,
	DEFAULT_ITEM,
	SANDBOX_OTP,
	run_compliance_smoke_test,
	run_zatca_sandbox_test,
	setup_zatca_cli,
	setup_zatca_sandbox,
	sync_sandbox_supplier_vat_with_production_cert,
	verify_zatca_cli,
)
from custom_erpnext.integrations.zatca.utils import is_ksa_compliance_installed

ZatcaEnv = Literal["Sandbox", "Simulation", "Production"]

PHASE_PORTALS = {
	"Sandbox": {
		"portal": "ZATCA Developer Portal (no login required)",
		"otp": "123345 (fixed test OTP)",
		"gateway": "https://gw-fatoora.zatca.gov.sa/e-invoicing/developer-portal/",
	},
	"Simulation": {
		"portal": "https://simulation.zatca.gov.sa",
		"otp": "6-digit OTP from Simulation Fatoora portal (valid ~1 hour)",
		"gateway": "https://gw-fatoora.zatca.gov.sa/e-invoicing/simulation/",
	},
	"Production": {
		"portal": "https://fatoora.zatca.gov.sa",
		"otp": "6-digit OTP from Production Fatoora portal (valid ~1 hour)",
		"gateway": "https://gw-fatoora.zatca.gov.sa/e-invoicing/core/",
	},
}


def _require_ksa_compliance() -> None:
	if not is_ksa_compliance_installed():
		frappe.throw("ksa_compliance is not installed on this site.")


def derive_company_unit(vat: str, branch_name: str = "Main Branch") -> str:
	"""Organization Unit Name for CSR — 10-digit TIN when VAT 11th digit is 1."""
	vat = (vat or "").strip()
	if len(vat) == 15 and vat[10] == "1":
		return vat[1:11]
	return branch_name


def _get_active_settings(company: str, fatoora_server: str | None = None):
	filters: dict[str, Any] = {"company": company, "status": "Active"}
	if fatoora_server:
		filters["fatoora_server"] = fatoora_server
	name = frappe.db.get_value("ZATCA Business Settings", filters, "name")
	if not name:
		return None
	return frappe.get_doc("ZATCA Business Settings", name)


def _company_address(company: str) -> str | None:
	return frappe.db.get_value(
		"Dynamic Link",
		{"link_doctype": "Company", "link_name": company, "parenttype": "Address"},
		"parent",
	)


def _validate_company_for_live(company: str) -> list[str]:
	issues: list[str] = []
	company_doc = frappe.get_doc("Company", company)
	vat = (company_doc.tax_id or "").strip()

	if company_doc.country != "Saudi Arabia":
		issues.append("Company country must be Saudi Arabia")
	if not vat or len(vat) != 15 or not vat.startswith("3") or not vat.endswith("3"):
		issues.append("Company tax_id must be a valid 15-digit Saudi VAT (starts/ends with 3)")

	address_name = _company_address(company)
	if not address_name:
		issues.append("Link a Saudi Arabia Address to the company")
		return issues

	address = frappe.get_doc("Address", address_name)
	if address.country != "Saudi Arabia":
		issues.append("Company address must be in Saudi Arabia")
	if not (address.get("custom_building_number") or "").strip():
		issues.append("Address custom_building_number is required")
	if not (address.get("custom_area") or "").strip():
		issues.append("Address custom_area (district) is required")
	if not (address.address_line1 or "").strip():
		issues.append("Address street (address_line1) is required")

	return issues


def revoke_current_settings(company: str) -> dict[str, Any]:
	"""Revoke active ZATCA Business Settings before switching environment."""
	from ksa_compliance.ksa_compliance.doctype.zatca_business_settings.zatca_business_settings import (
		revoke_business_settings,
	)

	settings = _get_active_settings(company)
	if not settings:
		return {"status": "nothing_to_revoke"}

	revoke_business_settings(settings.name, company)
	frappe.db.commit()
	return {"status": "revoked", "settings": settings.name}


def prepare_live_settings(
	company: str = DEFAULT_COMPANY,
	fatoora_server: ZatcaEnv = "Simulation",
	company_unit: str | None = None,
	company_unit_serial: str | None = None,
	crn: str | None = None,
	revoke_existing: int = 1,
) -> dict[str, Any]:
	"""
	Create ZATCA Business Settings for Simulation or Production.

	Set the company tax_id to your real VAT before calling this.
	"""
	_require_ksa_compliance()
	frappe.only_for("System Manager")

	if fatoora_server == "Sandbox":
		frappe.throw("Use setup_zatca_sandbox() for Sandbox. This helper is for Simulation/Production.")

	issues = _validate_company_for_live(company)
	if issues:
		frappe.throw("Company not ready for live ZATCA:\n" + "\n".join(f"- {i}" for i in issues))

	if revoke_existing:
		revoke_current_settings(company)

	company_doc = frappe.get_doc("Company", company)
	address_name = _company_address(company)
	vat = (company_doc.tax_id or "").strip()
	branch_name = frappe.db.get_value("Address", address_name, "address_title") or "Main Branch"
	unit = company_unit or derive_company_unit(vat, branch_name)
	serial = company_unit_serial or f"1-ERPNext|2-16|3-{company.upper()}-{fatoora_server.upper()}-001"

	settings = frappe.new_doc("ZATCA Business Settings")
	settings.company = company
	settings.company_address = address_name
	settings.currency = company_doc.default_currency or "SAR"
	settings.seller_name = company_doc.company_name or company
	settings.vat_registration_number = vat
	settings.company_unit = unit
	settings.company_unit_serial = serial
	settings.company_category = company_doc.domain or "Retail"
	settings.enable_zatca_integration = 1
	settings.sync_with_zatca = "Live"
	settings.type_of_business_transactions = "Let the system decide (both)"
	settings.fatoora_server = fatoora_server
	settings.cli_setup = "Automatic"
	settings.validate_generated_xml = 1
	settings.automatic_vat_account_configuration = 1
	settings.account_name = "VAT"
	settings.account_number = "2301"
	settings.tax_rate = 15
	settings.zatca_tax_category = "Standard rate"

	if crn:
		settings.append(
			"other_ids",
			{"type_name": "Commercial Registration Number", "type_code": "CRN", "value": crn},
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
	frappe.db.commit()

	cli_info = setup_zatca_cli(settings.name)
	return {
		"settings": settings.name,
		"fatoora_server": fatoora_server,
		"vat": vat,
		"company_unit": unit,
		"cli": cli_info,
		"cli_version": verify_zatca_cli(settings.name),
		"next_step": f"Onboard with OTP from {PHASE_PORTALS[fatoora_server]['portal']}",
	}


def onboard_settings(settings_id: str, otp: str) -> dict[str, Any]:
	"""Onboard (Compliance CSID) for any environment."""
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
		"fatoora_server": settings.fatoora_server,
	}


def obtain_production_csid(settings_id: str, otp: str, force: bool = False) -> dict[str, Any]:
	"""Get Production CSID (required before submitting real invoices in Simulation/Production)."""
	settings = frappe.get_doc("ZATCA Business Settings", settings_id)
	if settings.production_request_id and not force:
		vat_sync = (
			sync_sandbox_supplier_vat_with_production_cert(settings_id)
			if settings.fatoora_server == "Sandbox"
			else {"status": "skipped", "reason": "not_sandbox"}
		)
		return {
			"status": "already_obtained",
			"production_request_id": settings.production_request_id,
			"vat_sync": vat_sync,
		}

	settings.get_production_csid(otp)
	frappe.db.commit()
	settings.reload()

	vat_sync = (
		sync_sandbox_supplier_vat_with_production_cert(settings_id)
		if settings.fatoora_server == "Sandbox"
		else {"status": "skipped", "reason": "not_sandbox"}
	)
	return {
		"status": "obtained",
		"production_request_id": settings.production_request_id,
		"fatoora_server": settings.fatoora_server,
		"vat_sync": vat_sync,
	}


@frappe.whitelist()
def run_phase_sandbox(
	company: str = DEFAULT_COMPANY,
	item_id: str = DEFAULT_ITEM,
) -> dict[str, Any]:
	"""Phase 1: automated Sandbox setup + compliance smoke test."""
	frappe.set_user("Administrator")
	report = run_zatca_sandbox_test(company=company, item_id=item_id, run_setup=1)
	report["phase"] = "Sandbox"
	report["phase_passed"] = report.get("success")
	report["next_phase"] = "Simulation" if report.get("success") else None
	report["next_steps"] = (
		[
			"Sandbox passed. Revoke Sandbox settings when done testing.",
			"Set company tax_id to your REAL Saudi VAT number.",
			"Run prepare_phase_simulation() then onboard with Simulation portal OTP.",
		]
		if report.get("success")
		else ["Fix failing checks above, then re-run run_phase_sandbox()"]
	)
	return report


@frappe.whitelist()
def prepare_phase_simulation(
	company: str = DEFAULT_COMPANY,
	crn: str | None = None,
	revoke_existing: int = 1,
) -> dict[str, Any]:
	"""Phase 2 setup: create Simulation settings + CLI (OTP onboarding is a separate step)."""
	frappe.set_user("Administrator")
	result = prepare_live_settings(
		company=company,
		fatoora_server="Simulation",
		crn=crn,
		revoke_existing=revoke_existing,
	)
	result["phase"] = "Simulation"
	result["portal"] = PHASE_PORTALS["Simulation"]
	result["commands"] = {
		"onboard": f'bench --site <site> execute custom_erpnext.integrations.zatca.zatca_phases.onboard_phase --kwargs \'{{"company": "{company}", "otp": "<SIMULATION_OTP>"}}\'',
	}
	return result


@frappe.whitelist()
def prepare_phase_production(
	company: str = DEFAULT_COMPANY,
	crn: str | None = None,
	revoke_existing: int = 1,
) -> dict[str, Any]:
	"""Phase 3 setup: create Production settings + CLI."""
	frappe.set_user("Administrator")
	result = prepare_live_settings(
		company=company,
		fatoora_server="Production",
		crn=crn,
		revoke_existing=revoke_existing,
	)
	result["phase"] = "Production"
	result["portal"] = PHASE_PORTALS["Production"]
	return result


@frappe.whitelist()
def onboard_phase(
	company: str = DEFAULT_COMPANY,
	otp: str = "",
	fatoora_server: str | None = None,
) -> dict[str, Any]:
	"""Onboard active settings with OTP (Simulation or Production)."""
	frappe.set_user("Administrator")
	if not otp:
		frappe.throw("OTP is required. Get it from the Fatoora portal for your environment.")

	settings = _get_active_settings(company, fatoora_server)
	if not settings:
		frappe.throw(f"No active ZATCA Business Settings found for {company}")

	if not settings.zatca_cli_path:
		setup_zatca_cli(settings.name)

	return onboard_settings(settings.name, otp)


@frappe.whitelist()
def run_phase_compliance_test(
	company: str = DEFAULT_COMPANY,
	item_id: str = DEFAULT_ITEM,
	fatoora_server: str | None = None,
) -> dict[str, Any]:
	"""Run simplified + standard compliance smoke test for the active environment."""
	frappe.set_user("Administrator")
	settings = _get_active_settings(company, fatoora_server)
	if not settings:
		frappe.throw("No active ZATCA Business Settings found")

	if not settings.compliance_request_id:
		frappe.throw("Not onboarded yet. Run onboard_phase() first.")

	results = run_compliance_smoke_test(settings.name, item_id=item_id)
	passed = all(row.get("passed") for row in results.values())
	return {
		"phase": settings.fatoora_server,
		"settings": settings.name,
		"compliance_checks": results,
		"passed": passed,
		"next_step": (
			"Run obtain_production_csid_phase() with a fresh OTP"
			if passed and not settings.production_request_id
			else None
		),
	}


@frappe.whitelist()
def obtain_production_csid_phase(
	company: str = DEFAULT_COMPANY,
	otp: str = "",
	fatoora_server: str | None = None,
) -> dict[str, Any]:
	"""Obtain Production CSID after compliance checks pass."""
	frappe.set_user("Administrator")
	if not otp:
		frappe.throw("OTP is required.")

	settings = _get_active_settings(company, fatoora_server)
	if not settings:
		frappe.throw("No active ZATCA Business Settings found")

	return obtain_production_csid(settings.name, otp)


@frappe.whitelist()
def get_phase_status(company: str = DEFAULT_COMPANY) -> dict[str, Any]:
	"""Show progress through Sandbox → Simulation → Production."""
	frappe.only_for("System Manager")

	status: dict[str, Any] = {
		"company": company,
		"checked_at": str(now_datetime()),
		"phases": {},
		"current_environment": None,
		"recommended_next_action": None,
	}

	active = _get_active_settings(company)
	if active:
		status["current_environment"] = active.fatoora_server
		status["active_settings"] = active.name

	for env in ("Sandbox", "Simulation", "Production"):
		row = frappe.db.get_value(
			"ZATCA Business Settings",
			{"company": company, "fatoora_server": env, "status": "Active"},
			["name", "compliance_request_id", "production_request_id", "vat_registration_number"],
			as_dict=True,
		)
		if not row:
			revoked = frappe.db.count(
				"ZATCA Business Settings", {"company": company, "fatoora_server": env, "status": "Revoked"}
			)
			status["phases"][env] = {
				"status": "not_started" if not revoked else "revoked",
				"portal": PHASE_PORTALS[env],
			}
			continue

		readiness = check_production_readiness(
			company=company,
			target_env=env,
			require_production_csid=int(env != "Sandbox"),
		)
		status["phases"][env] = {
			"status": "active",
			"settings": row.name,
			"vat": row.vat_registration_number,
			"onboarded": bool(row.compliance_request_id),
			"production_csid": bool(row.production_request_id),
			"ready": readiness.get("ready_for_production") or readiness.get("ready_for_sandbox_testing"),
			"blocking_issues": readiness.get("blocking_issues", []),
			"portal": PHASE_PORTALS[env],
		}

	# Recommend next action
	sandbox = status["phases"].get("Sandbox", {})
	simulation = status["phases"].get("Simulation", {})
	production = status["phases"].get("Production", {})

	if sandbox.get("status") != "active" or not sandbox.get("onboarded"):
		status["recommended_next_action"] = "run_phase_sandbox()"
	elif sandbox.get("status") == "active" and sandbox.get("ready"):
		status["recommended_next_action"] = (
			"Sandbox complete → revoke Sandbox settings → prepare_phase_simulation() → onboard with Simulation OTP"
		)
	elif simulation.get("status") != "active":
		status["recommended_next_action"] = "prepare_phase_simulation() then onboard_phase(otp=...)"
	elif simulation.get("status") == "active" and not simulation.get("onboarded"):
		status["recommended_next_action"] = "onboard_phase(otp=<from simulation.zatca.gov.sa>)"
	elif simulation.get("status") == "active" and not simulation.get("production_csid"):
		status["recommended_next_action"] = (
			"run_phase_compliance_test() then obtain_production_csid_phase(otp=...)"
		)
	elif simulation.get("ready") and production.get("status") != "active":
		status["recommended_next_action"] = (
			"Simulation complete → revoke → prepare_phase_production() → onboard → compliance → production CSID"
		)
	elif production.get("status") == "active" and production.get("ready"):
		status["recommended_next_action"] = "Production ready — submit live invoices"
	else:
		status["recommended_next_action"] = "Complete Production onboarding and compliance checks"

	return status


def main(action: str = "status", company: str = DEFAULT_COMPANY, item_id: str = DEFAULT_ITEM) -> None:
	"""
	CLI entry point for phased ZATCA testing.

	Examples:
	  bench --site tsc.localhost execute custom_erpnext.integrations.zatca.zatca_phases.main
	  bench --site tsc.localhost execute custom_erpnext.integrations.zatca.zatca_phases.main --kwargs '{"action": "sandbox"}'
	  bench --site tsc.localhost execute custom_erpnext.integrations.zatca.zatca_phases.main --kwargs '{"action": "status"}'
	"""
	frappe.set_user("Administrator")
	actions = {
		"status": lambda: get_phase_status(company=company),
		"sandbox": lambda: run_phase_sandbox(company=company, item_id=item_id),
		"prepare_simulation": lambda: prepare_phase_simulation(company=company),
		"prepare_production": lambda: prepare_phase_production(company=company),
	}
	if action not in actions:
		frappe.throw(f"Unknown action '{action}'. Use: {', '.join(actions)}")

	result = actions[action]()
	print(json.dumps(result, indent=2, default=str))
