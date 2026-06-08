# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class UserDiscountProfile(Document):
	def validate(self):
		default_branches = [row.branch for row in self.allowed_branches if row.is_default]
		if len(default_branches) > 1:
			frappe.throw(_("Only one default branch is allowed per user profile"))

		if self.max_discount_percent and self.max_discount_percent > 100:
			frappe.throw(_("Max Discount % cannot exceed 100"))
