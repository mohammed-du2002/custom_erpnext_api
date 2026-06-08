# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class PurchaseInvoiceAddon(Document):
	def validate(self):
		if self.is_percentage and not self.percentage:
			frappe.throw(_("Percentage is required when Is Percentage is checked"))

		if not self.is_percentage and not self.amount:
			frappe.throw(_("Amount is required when not using percentage"))
