# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, now_datetime


class SyncConfiguration(Document):
	def validate(self):
		if self.batch_size and self.batch_size <= 0:
			frappe.throw(_("Batch Size must be greater than zero"))

		if self.timeout_seconds and self.timeout_seconds <= 0:
			frappe.throw(_("Timeout must be greater than zero"))

	def before_save(self):
		if self.is_active and self.frequency and not self.next_sync_time:
			self.next_sync_time = self.get_next_sync_time()

	def get_next_sync_time(self):
		now = now_datetime()
		frequency_map = {
			"Every 10 Minutes": {"minutes": 10},
			"Hourly": {"hours": 1},
			"Daily": {"days": 1},
		}
		if self.frequency in frequency_map:
			return add_to_date(now, **frequency_map[self.frequency])
		return now
