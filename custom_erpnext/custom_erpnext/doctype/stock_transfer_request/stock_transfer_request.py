# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


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

		self.compute_transfer_pricing()

	def on_cancel(self):
		self.db_set("status", "Cancelled")

	def compute_transfer_pricing(self):
		"""Transfer pricing per SRS §3.8: Cost/Selling/Special rate + margin, with
		additional expenses distributed onto each item's landed cost."""
		method = self.get("pricing_method") or "Cost"
		margin_factor = 1 + flt(self.get("margin_percent")) / 100.0

		total = 0.0
		for row in self.items:
			base_rate = self._base_transfer_rate(row, method)
			row.rate = flt(flt(base_rate) * margin_factor, 6)
			row.amount = flt(flt(row.rate) * flt(row.qty), 6)
			total += flt(row.amount)

		expenses = flt(self.get("additional_expenses"))
		for row in self.items:
			share = (flt(row.amount) / total * expenses) if total else 0.0
			row.landed_rate = (
				flt((flt(row.amount) + share) / flt(row.qty), 6) if flt(row.qty) else 0.0
			)

		self.total_transfer_value = flt(total + expenses, 6)

	def _base_transfer_rate(self, row, method):
		if method == "Special":
			return flt(row.get("special_rate"))

		if method == "Selling":
			return flt(frappe.db.get_value("Item", row.item_code, "standard_rate"))

		# Cost: moving-average valuation at the source warehouse.
		return flt(
			frappe.db.get_value(
				"Bin", {"item_code": row.item_code, "warehouse": self.from_warehouse}, "valuation_rate"
			)
		)


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
