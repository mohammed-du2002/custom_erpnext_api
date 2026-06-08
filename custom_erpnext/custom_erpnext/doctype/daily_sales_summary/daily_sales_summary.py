# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class DailySalesSummary(Document):
	def validate(self):
		if self.total_sales or self.total_returns:
			self.net_sales = (self.total_sales or 0) - (self.total_returns or 0)

		if self.transaction_count and self.net_sales:
			self.average_ticket = self.net_sales / self.transaction_count

		if self.opening_cash is not None and self.closing_cash is not None:
			expected = (self.opening_cash or 0) + (self.cash_sales or 0)
			self.variance = (self.closing_cash or 0) - expected

		if self.status == "Synced":
			self.synced_to_erp = 1
