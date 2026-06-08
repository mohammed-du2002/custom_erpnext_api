# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class PaymentMethodConfig(Document):
	def validate(self):
		self.validate_unique_branch_method()

	def validate_unique_branch_method(self):
		existing = frappe.db.get_value(
			"Payment Method Config",
			{
				"branch": self.branch,
				"payment_method": self.payment_method,
				"name": ["!=", self.name],
			},
			"name",
		)
		if existing:
			frappe.throw(
				_("Payment Method Config already exists for {0} - {1}").format(
					frappe.bold(self.branch), frappe.bold(self.payment_method)
				)
			)
