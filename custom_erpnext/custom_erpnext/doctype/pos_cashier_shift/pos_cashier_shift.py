# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt


class POSCashierShift(Document):
	def validate(self):
		if self.opening_cash is not None and self.closing_cash is not None and self.status == "Closed":
			expected = flt(self.expected_cash)
			self.variance = flt(self.closing_cash) - expected
