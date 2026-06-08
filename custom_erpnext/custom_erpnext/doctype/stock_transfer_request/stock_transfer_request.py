# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class StockTransferRequest(Document):
	def before_insert(self):
		if not self.request_number:
			self.request_number = self.name

	def validate(self):
		if self.from_warehouse == self.to_warehouse:
			frappe.throw(_("From Warehouse and To Warehouse cannot be the same"))

		if not self.items:
			frappe.throw(_("At least one item is required"))

		for row in self.items:
			if row.qty <= 0:
				frappe.throw(_("Row {0}: Qty must be greater than zero").format(row.idx))

	def on_cancel(self):
		self.db_set("status", "Cancelled")


@frappe.whitelist()
def approve_transfer(name):
	"""Legacy API helper — prefer workflow Approve action."""
	doc = frappe.get_doc("Stock Transfer Request", name)
	if doc.status != "Pending":
		frappe.throw(_("Only pending requests can be approved"))

	doc.status = "Approved"
	doc.approved_by = frappe.session.user
	doc.save(ignore_permissions=True)
	return doc.name
