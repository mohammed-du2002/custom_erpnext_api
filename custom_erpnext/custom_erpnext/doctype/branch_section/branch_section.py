# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class BranchSection(Document):
	def validate(self):
		self.section_code = (self.section_code or "").strip().upper()
		if not self.section_code:
			frappe.throw(_("Section Code is required"))

		if self.branch and not frappe.db.get_value("Company Branch", self.branch, "is_active"):
			frappe.throw(_("Branch {0} is not active").format(frappe.bold(self.branch)))
