# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Verify Phase A foundation: branches, sections, company/warehouse/user custom fields."""

import frappe
from frappe import ValidationError


def run_phase_a_verification():
	frappe.set_user("Administrator")
	results = {"passed": [], "failed": [], "warnings": []}

	def check(name, condition, msg=""):
		if condition:
			results["passed"].append(name)
		else:
			results["failed"].append(f"{name}: {msg}")

	_check_doctypes(check)
	_check_custom_fields(check)
	_check_validations(check)
	_check_foundation_validations(check)
	_check_permissions(check)
	results["warnings"] = _check_data(check)

	frappe.db.rollback()
	return results


def _check_doctypes(check):
	for dt in ("Company Branch", "Branch Section", "Warehouse Location", "User Section Access"):
		check(f"doctype_{dt.replace(' ', '_').lower()}", frappe.db.exists("DocType", dt), "missing DocType")


def _check_custom_fields(check):
	for dt, fields in {
		"Company": (
			"retail_settings_section",
			"number_of_branches",
			"default_cost_center",
			"central_warehouse",
			"party_account_model",
		),
		"Warehouse": (
			"retail_warehouse_section",
			"branch",
			"retail_warehouse_type",
			"location",
			"manager",
			"is_pos_warehouse",
			"allow_negative_stock",
			"bin_locations",
		),
		"User": (
			"retail_access_section",
			"employee_id",
			"branch",
			"sections",
			"max_discount",
			"pos_access",
			"erp_access",
		),
	}.items():
		meta_fields = {f.fieldname for f in frappe.get_meta(dt).fields}
		for fieldname in fields:
			check(f"{dt.lower()}_field_{fieldname}", fieldname in meta_fields, "missing custom field")


def _check_validations(check):
	company = frappe.db.get_single_value("Global Defaults", "default_company")
	if not company:
		company = frappe.get_all("Company", pluck="name", limit=1)[0]

	doc = frappe.get_doc(
		{
			"doctype": "Company Branch",
			"branch_code": " testcode ",
			"branch_name": "Test Code",
			"company": company,
		}
	)
	doc.validate_branch_code()
	check("branch_code_uppercase", doc.branch_code == "TESTCODE", doc.branch_code)

	wrong_company = frappe.get_all("Company", filters={"name": ["!=", company]}, pluck="name", limit=1)
	if wrong_company:
		wrong_cc = frappe.db.get_value(
			"Cost Center", {"company": wrong_company[0], "is_group": 0}, "name"
		)
		if wrong_cc:
			try:
				bad = frappe.get_doc(
					{
						"doctype": "Company Branch",
						"branch_code": "BADCC",
						"branch_name": "Bad CC",
						"company": company,
						"cost_center": wrong_cc,
					}
				)
				bad.validate_company_links()
				check("branch_rejects_foreign_cost_center", False, "should throw")
			except ValidationError:
				check("branch_rejects_foreign_cost_center", True, "")

	branches = frappe.get_all("Company Branch", pluck="name", limit=1)
	if branches:
		inactive = branches[0]
		frappe.db.set_value("Company Branch", inactive, "is_active", 0, update_modified=False)
		try:
			sec = frappe.get_doc(
				{
					"doctype": "Branch Section",
					"section_code": "TSTSEC",
					"section_name": "Test",
					"branch": inactive,
				}
			)
			sec.validate()
			check("section_rejects_inactive_branch", False, "should throw")
		except ValidationError:
			check("section_rejects_inactive_branch", True, "")
		finally:
			frappe.db.set_value("Company Branch", inactive, "is_active", 1, update_modified=False)


def _check_foundation_validations(check):
	from custom_erpnext.services.foundation_service import validate_user_retail_fields

	try:
		user = frappe.get_doc({"doctype": "User", "email": "qa@test.local", "first_name": "QA", "max_discount": 150})
		validate_user_retail_fields(user)
		check("user_rejects_invalid_discount", False, "should throw")
	except frappe.ValidationError:
		check("user_rejects_invalid_discount", True, "")

	company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.get_all(
		"Company", pluck="name", limit=1
	)[0]
	warehouse = frappe.db.get_value("Warehouse", {"company": company, "is_group": 0}, "name")
	if warehouse:
		from custom_erpnext.services.foundation_service import validate_company_retail_fields

		doc = frappe.get_doc("Company", company)
		doc.central_warehouse = warehouse
		try:
			validate_company_retail_fields(doc)
			check("company_accepts_own_warehouse", True, "")
		except frappe.ValidationError:
			check("company_accepts_own_warehouse", False, "valid warehouse rejected")


def _check_permissions(check):
	from custom_erpnext.services.branch_permission_service import (
		BRANCH_ISOLATED_DOCTYPES,
		get_permission_query_conditions,
	)

	for dt in ("Company Branch", "Branch Section", "Warehouse"):
		check(
			f"permission_hook_{dt.replace(' ', '_').lower()}",
			dt in BRANCH_ISOLATED_DOCTYPES,
			"not isolated",
		)
		check(
			f"admin_bypass_{dt.replace(' ', '_').lower()}",
			get_permission_query_conditions("Administrator", dt) == "",
			"admin should bypass",
		)


def _check_data(check):
	cb_count = frappe.db.count("Company Branch")
	bs_count = frappe.db.count("Branch Section")
	check("has_company_branches", cb_count > 0, f"count={cb_count}")
	warnings = [f"Company Branches: {cb_count}, Branch Sections: {bs_count}"]

	for wh in frappe.get_all(
		"Warehouse", filters={"branch": ["is", "set"]}, fields=["name", "branch", "company"], limit=20
	):
		branch_company = frappe.db.get_value("Company Branch", wh.branch, "company")
		check(
			f"wh_company_match_{wh.name}",
			branch_company == wh.company,
			f"branch company {branch_company} != warehouse company {wh.company}",
		)

	return warnings


@frappe.whitelist()
def print_phase_a_report():
	results = run_phase_a_verification()
	print("\n=== PHASE A VERIFICATION ===")
	print(f"PASSED: {len(results['passed'])}")
	print(f"FAILED: {len(results['failed'])}")
	for item in results["failed"]:
		print(f"  FAIL: {item}")
	for item in results.get("warnings", []):
		print(f"  INFO: {item}")
	return results
