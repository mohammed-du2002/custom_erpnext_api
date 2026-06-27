# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Seed default Branch Section records for active Company Branches."""

import frappe

DEFAULT_SECTIONS = (
	{"section_code": "SALES", "section_name": "Sales Floor"},
	{"section_code": "BACK", "section_name": "Back Store"},
	{"section_code": "POS", "section_name": "POS Area"},
)


@frappe.whitelist()
def seed_default_branch_sections():
	"""Create standard sections for every active branch. Idempotent."""
	created = []

	for branch in frappe.get_all("Company Branch", filters={"is_active": 1}, pluck="name"):
		for section_def in DEFAULT_SECTIONS:
			code = f"{branch}-{section_def['section_code']}"
			if frappe.db.exists("Branch Section", code):
				continue

			doc = frappe.get_doc(
				{
					"doctype": "Branch Section",
					"section_code": code,
					"section_name": section_def["section_name"],
					"branch": branch,
					"is_active": 1,
				}
			)
			doc.insert(ignore_permissions=True)
			created.append(code)

	frappe.db.commit()
	return {"created": created, "total_sections": frappe.db.count("Branch Section")}
