# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class POSDevice(Document):
	def validate(self):
		self.device_id = (self.device_id or "").strip()
		if not self.device_id:
			frappe.throw(_("Device ID is required"))

		if self.branch and self.warehouse:
			branch_company = frappe.db.get_value("Company Branch", self.branch, "company")
			warehouse_company = frappe.db.get_value("Warehouse", self.warehouse, "company")
			if branch_company and warehouse_company and branch_company != warehouse_company:
				frappe.throw(_("Warehouse does not belong to the same company as the branch"))
