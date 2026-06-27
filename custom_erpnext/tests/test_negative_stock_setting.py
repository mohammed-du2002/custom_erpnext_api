# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Regression tests for BUG-01: retail POS must allow negative selling (SRS §8.4)."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import cint

from custom_erpnext.setup.stock_settings import enable_negative_stock_for_retail


class TestNegativeStockSetting(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_enables_when_disabled(self):
		frappe.db.set_single_value("Stock Settings", "allow_negative_stock", 0)

		changed = enable_negative_stock_for_retail()

		self.assertTrue(changed)
		self.assertEqual(
			cint(frappe.db.get_single_value("Stock Settings", "allow_negative_stock")), 1
		)

	def test_idempotent_when_already_enabled(self):
		frappe.db.set_single_value("Stock Settings", "allow_negative_stock", 1)

		changed = enable_negative_stock_for_retail()

		self.assertFalse(changed)
		self.assertEqual(
			cint(frappe.db.get_single_value("Stock Settings", "allow_negative_stock")), 1
		)
