# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ZATCAConfiguration(Document):
	def validate(self):
		if self.environment == "Production" and not self.csid_production:
			frappe.throw(_("CSID Production is required for Production environment"))
