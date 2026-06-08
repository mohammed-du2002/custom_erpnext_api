# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ZATCAInvoice(Document):
	def validate(self):
		if self.invoice and frappe.db.get_value("Sales Invoice", self.invoice, "docstatus") != 1:
			frappe.throw(_("Sales Invoice must be submitted before creating a ZATCA Invoice record"))

	def on_update(self):
		self.sync_sales_invoice_fields()

	def sync_sales_invoice_fields(self):
		"""Mirror key ZATCA fields to Sales Invoice for display."""
		if not self.invoice:
			return

		status_map = {
			"Draft": "Pending",
			"Submitted": "Pending",
			"Cleared": "Cleared",
			"Reported": "Reported",
			"Rejected": "Rejected",
		}

		frappe.db.set_value(
			"Sales Invoice",
			self.invoice,
			{
				"zatca_uuid": self.zatca_uuid,
				"zatca_status": status_map.get(self.submission_status, "Pending"),
			},
			update_modified=False,
		)
