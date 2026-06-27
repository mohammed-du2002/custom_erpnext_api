# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Phase A foundation validations for Company, Warehouse, and User."""

import frappe
from frappe import _
from frappe.utils import flt


def validate_company_retail_fields(doc, method=None):
	if doc.get("default_cost_center"):
		cc_company = frappe.db.get_value("Cost Center", doc.default_cost_center, "company")
		if cc_company and cc_company != doc.name:
			frappe.throw(
				_("Default Cost Center {0} does not belong to Company {1}").format(
					frappe.bold(doc.default_cost_center), frappe.bold(doc.name)
				)
			)

	if doc.get("central_warehouse"):
		wh_company = frappe.db.get_value("Warehouse", doc.central_warehouse, "company")
		if wh_company and wh_company != doc.name:
			frappe.throw(
				_("Central Warehouse {0} does not belong to Company {1}").format(
					frappe.bold(doc.central_warehouse), frappe.bold(doc.name)
				)
			)

	if doc.get("number_of_branches") is not None and doc.number_of_branches < 0:
		frappe.throw(_("Number of Branches cannot be negative"))


def validate_warehouse_branch(doc, method=None):
	if not doc.get("branch"):
		return

	branch_row = frappe.db.get_value(
		"Company Branch",
		doc.branch,
		["company", "is_active"],
		as_dict=True,
	)
	if not branch_row:
		frappe.throw(_("Company Branch {0} does not exist").format(frappe.bold(doc.branch)))

	if not branch_row.is_active:
		frappe.throw(_("Company Branch {0} is not active").format(frappe.bold(doc.branch)))

	if branch_row.company != doc.company:
		frappe.throw(
			_("Branch {0} belongs to Company {1}, not {2}").format(
				frappe.bold(doc.branch),
				frappe.bold(branch_row.company),
				frappe.bold(doc.company),
			)
		)


def validate_user_retail_fields(doc, method=None):
	if doc.get("max_discount") is not None:
		max_discount = flt(doc.max_discount)
		if max_discount < 0 or max_discount > 100:
			frappe.throw(_("Max Discount % must be between 0 and 100"))

	if doc.get("branch"):
		if not frappe.db.get_value("Company Branch", doc.branch, "is_active"):
			frappe.throw(_("Default Branch {0} is not active").format(frappe.bold(doc.branch)))

	for row in doc.get("sections") or []:
		if not row.section:
			continue

		section_branch = frappe.db.get_value("Branch Section", row.section, "branch")
		if not section_branch:
			continue

		if doc.branch and section_branch != doc.branch:
			frappe.throw(
				_("Section {0} belongs to branch {1}, not user branch {2}").format(
					frappe.bold(row.section),
					frappe.bold(section_branch),
					frappe.bold(doc.branch),
				)
			)

		if not frappe.db.get_value("Branch Section", row.section, "is_active"):
			frappe.throw(_("Section {0} is not active").format(frappe.bold(row.section)))
