# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CompanyBranch(Document):
	def validate(self):
		self.validate_branch_code()
		self.validate_company_links()

	def on_update(self):
		from custom_erpnext.services.naming_series_service import register_branch_naming_series

		register_branch_naming_series(self)

	def validate_branch_code(self):
		self.branch_code = (self.branch_code or "").strip().upper()
		if not self.branch_code:
			frappe.throw(_("Branch Code is required"))

	def validate_company_links(self):
		if self.cost_center:
			cost_center_company = frappe.db.get_value("Cost Center", self.cost_center, "company")
			if cost_center_company and cost_center_company != self.company:
				frappe.throw(
					_("Cost Center {0} does not belong to Company {1}").format(
						frappe.bold(self.cost_center), frappe.bold(self.company)
					)
				)

		if self.warehouse:
			warehouse_company = frappe.db.get_value("Warehouse", self.warehouse, "company")
			if warehouse_company and warehouse_company != self.company:
				frappe.throw(
					_("Warehouse {0} does not belong to Company {1}").format(
						frappe.bold(self.warehouse), frappe.bold(self.company)
					)
				)
