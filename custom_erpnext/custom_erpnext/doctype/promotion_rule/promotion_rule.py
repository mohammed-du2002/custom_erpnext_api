# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class PromotionRule(Document):
	def validate(self):
		self.promotion_code = (self.promotion_code or "").strip().upper()
		if not self.promotion_code:
			frappe.throw(_("Promotion Code is required"))

		if self.start_date and self.end_date and getdate(self.end_date) < getdate(self.start_date):
			frappe.throw(_("End Date cannot be before Start Date"))

		if self.usage_limit and self.usage_count and self.usage_count > self.usage_limit:
			frappe.throw(_("Usage Count cannot exceed Usage Limit"))
