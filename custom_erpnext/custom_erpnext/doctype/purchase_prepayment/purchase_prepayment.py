# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


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

		self.validate_allocated_amount()
		self.set_remaining_amount()

	def validate_allocated_amount(self):
		if flt(self.get("allocated_amount")) > flt(self.amount):
			frappe.throw(
				_("Allocated Amount {0} cannot exceed prepayment amount {1}").format(
					flt(self.allocated_amount), flt(self.amount)
				)
			)

	def resolve_allocated_amount(self):
		"""Support partial allocation (SRS §4.6).

		Prefer an explicit ``allocated_amount``; otherwise fall back to the legacy
		full-allocation behaviour driven by ``allocated_to_invoice`` + status.
		"""
		allocated = flt(self.get("allocated_amount"))
		if not allocated and self.allocated_to_invoice and self.status == "Allocated":
			allocated = flt(self.amount)
		return min(allocated, flt(self.amount))

	def set_remaining_amount(self):
		if not self.amount:
			self.allocated_amount = 0
			self.remaining_amount = 0
			return

		allocated = self.resolve_allocated_amount()
		self.allocated_amount = allocated
		self.remaining_amount = flt(self.amount) - allocated

		# Keep status in sync with the allocation level (do not override Refunded).
		if self.status != "Refunded":
			if allocated <= 0:
				if self.status in ("Allocated", "Partially Allocated"):
					self.status = "Paid"
			elif allocated < flt(self.amount):
				self.status = "Partially Allocated"
			else:
				self.status = "Allocated"
