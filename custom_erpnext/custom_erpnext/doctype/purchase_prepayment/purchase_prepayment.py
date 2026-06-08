# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class PurchasePrepayment(Document):
	def validate(self):
		if self.amount and self.amount <= 0:
			frappe.throw(_("Amount must be greater than zero"))

		if self.po_reference:
			po_supplier = frappe.db.get_value("Purchase Order", self.po_reference, "supplier")
			if po_supplier and po_supplier != self.supplier:
				frappe.throw(
					_("Purchase Order {0} does not belong to Supplier {1}").format(
						frappe.bold(self.po_reference), frappe.bold(self.supplier)
					)
				)

		if self.allocated_to_invoice:
			allocated = frappe.db.get_value(
				"Purchase Invoice", self.allocated_to_invoice, ["supplier", "grand_total"], as_dict=True
			)
			if allocated and allocated.supplier != self.supplier:
				frappe.throw(_("Purchase Invoice supplier does not match prepayment supplier"))

		self.set_remaining_amount()

	def set_remaining_amount(self):
		if not self.amount:
			self.remaining_amount = 0
			return

		allocated_amount = 0
		if self.allocated_to_invoice and self.status == "Allocated":
			allocated_amount = self.amount

		self.remaining_amount = (self.amount or 0) - allocated_amount
