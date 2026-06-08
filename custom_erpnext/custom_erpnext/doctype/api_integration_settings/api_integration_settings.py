# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class APIIntegrationSettings(Document):
	def validate(self):
		if self.request_timeout and self.request_timeout <= 0:
			frappe.throw(_("Request Timeout must be greater than zero"))

		if self.rate_limit_per_minute and self.rate_limit_per_minute <= 0:
			frappe.throw(_("Rate Limit must be greater than zero"))
