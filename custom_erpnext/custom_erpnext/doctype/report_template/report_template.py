# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document


class ReportTemplate(Document):
	def validate(self):
		for fieldname in ("filters", "chart_config"):
			value = self.get(fieldname)
			if value:
				try:
					json.loads(value)
				except json.JSONDecodeError as err:
					frappe.throw(_("{0} must be valid JSON: {1}").format(fieldname, str(err)))
