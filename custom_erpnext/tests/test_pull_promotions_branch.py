# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Regression tests for BUG-14: pull_promotions branch filtering + pagination.

The previous implementation paginated at the DB level and then filtered by
branch in Python, so ``total`` reflected only one page and branch promotions
living on later pages were dropped. These tests assert DB-level filtering with
correct totals and full cross-page coverage.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from custom_erpnext.services.pull_service import pull_promotions

PREFIX = "ZZTEST-PROMO-"


class TestPullPromotionsBranch(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.branches = frappe.get_all("Company Branch", filters={"is_active": 1}, pluck="name")

	def tearDown(self):
		frappe.db.rollback()

	def _make_promo(self, suffix, branch_rows=None):
		code = f"{PREFIX}{suffix}"
		doc = frappe.get_doc(
			{
				"doctype": "Promotion Rule",
				"promotion_name": code,
				"promotion_code": code,
				"promotion_type": "Percentage Discount",
				"is_active": 1,
				"start_date": today(),
				"end_date": add_days(today(), 30),
				"discount_percent": 10,
			}
		)
		for branch in branch_rows or []:
			doc.append("applicable_branches", {"branch": branch, "is_active": 1})
		doc.insert(ignore_permissions=True)
		return doc.name

	def _collect_all(self, branch, page_size):
		records = []
		page = 1
		total = 0
		while True:
			recs, total = pull_promotions(branch=branch, page=page, page_size=page_size)
			records.extend(recs)
			if not recs or page * page_size >= total:
				break
			page += 1
		return records, total

	def test_branch_filtering_and_pagination(self):
		if not self.branches:
			self.skipTest("No active Company Branch available")

		branch_a = self.branches[0]

		# 3 global promotions (visible to every branch) + 2 restricted to branch A.
		global_names = {self._make_promo(f"G{i}") for i in range(3)}
		branch_a_names = {self._make_promo(f"A{i}", branch_rows=[branch_a]) for i in range(2)}
		expected_for_a = global_names | branch_a_names

		# Walk every page with a small page_size to exercise cross-page coverage.
		records, total = self._collect_all(branch_a, page_size=2)
		names = [r["name"] for r in records]

		# Pagination integrity: collecting every page returns exactly `total` rows
		# with no duplicates (the core BUG-14 regression).
		self.assertEqual(len(names), total)
		self.assertEqual(len(names), len(set(names)))

		# All promotions visible to branch A must be returned across pages.
		self.assertTrue(expected_for_a.issubset(set(names)))

	def test_other_branch_promotions_excluded(self):
		if len(self.branches) < 2:
			self.skipTest("Need at least two active branches")

		branch_a, branch_b = self.branches[0], self.branches[1]
		global_name = self._make_promo("G-SHARED")
		only_b = self._make_promo("ONLY-B", branch_rows=[branch_b])

		records, _ = self._collect_all(branch_a, page_size=50)
		names = {r["name"] for r in records}

		self.assertIn(global_name, names)
		self.assertNotIn(only_b, names)
