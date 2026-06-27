# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Regression tests for BUG-07: stock transfer pricing/margin/expense (SRS §3.8)."""

import frappe
from frappe.tests.utils import FrappeTestCase


class TestStockTransferPricing(FrappeTestCase):
	def _doc(self, method="Special", margin=10, expenses=30):
		doc = frappe.new_doc("Stock Transfer Request")
		doc.from_warehouse = "ZZ-WH-A"
		doc.to_warehouse = "ZZ-WH-B"
		doc.pricing_method = method
		doc.margin_percent = margin
		doc.additional_expenses = expenses

		r1 = doc.append("items", {"item_code": "ZZ-ITEM-A", "qty": 2})
		r1.special_rate = 100
		r2 = doc.append("items", {"item_code": "ZZ-ITEM-B", "qty": 4})
		r2.special_rate = 50
		return doc

	def test_special_pricing_margin_and_expense_allocation(self):
		doc = self._doc()
		doc.compute_transfer_pricing()

		i1, i2 = doc.items
		# Margin applied: 100*1.1 and 50*1.1
		self.assertEqual(i1.rate, 110)
		self.assertEqual(i1.amount, 220)
		self.assertEqual(i2.rate, 55)
		self.assertEqual(i2.amount, 220)

		# Total value = item total (440) + expenses (30)
		self.assertEqual(doc.total_transfer_value, 470)

		# Expenses split 50/50 by amount -> 15 each, folded into landed rate.
		self.assertEqual(i1.landed_rate, 117.5)  # (220 + 15) / 2
		self.assertEqual(i2.landed_rate, 58.75)  # (220 + 15) / 4

	def test_zero_expenses_landed_equals_rate(self):
		doc = self._doc(expenses=0)
		doc.compute_transfer_pricing()
		for row in doc.items:
			self.assertEqual(row.landed_rate, row.rate)
