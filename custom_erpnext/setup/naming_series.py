# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe

from custom_erpnext.services.naming_series_service import register_branch_naming_series


def sync_all_branch_naming_series():
	for branch_name in frappe.get_all("Company Branch", pluck="name"):
		register_branch_naming_series(frappe.get_doc("Company Branch", branch_name))

	frappe.db.commit()
