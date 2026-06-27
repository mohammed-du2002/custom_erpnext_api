# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Regression tests for BUG-13: incremental stock pull via Bin.modified."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from custom_erpnext.services.pull_service import pull_stock


class TestPullStockIncremental(FrappeTestCase):
	def test_modified_from_filters_bins(self):
		bin_row = frappe.get_all("Bin", fields=["warehouse"], limit=1)
		if not bin_row:
			self.skipTest("No Bin records available")
		warehouse = bin_row[0].warehouse

		_all, total_all, _wh = pull_stock(warehouse=warehouse)

		future = add_to_date(now_datetime(), days=5)
		recs_future, total_future, _wh = pull_stock(warehouse=warehouse, modified_from=future)
		self.assertEqual(total_future, 0)
		self.assertEqual(len(recs_future), 0)

		recs_past, total_past, _wh = pull_stock(
			warehouse=warehouse, modified_from="2000-01-01 00:00:00"
		)
		self.assertEqual(total_past, total_all)
		# Modified cursor is exposed so the middleware can advance it.
		if recs_past:
			self.assertIn("modified", recs_past[0])

	def test_requires_warehouse_or_branch(self):
		with self.assertRaises(frappe.ValidationError):
			pull_stock()
