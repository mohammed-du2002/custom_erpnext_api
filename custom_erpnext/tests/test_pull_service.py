# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Unit tests for the pull query layer (ERPNext -> POS reads)."""

import frappe
from frappe.tests import IntegrationTestCase

from custom_erpnext.services import pull_service

BRANCH = "BR1"


class TestPullService(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.has_branch = frappe.db.exists("Company Branch", BRANCH)

	def setUp(self):
		if not self.has_branch:
			self.skipTest(f"{BRANCH} not seeded")

	def test_get_modified_filter_valid(self):
		f = pull_service.get_modified_filter("2026-01-01 00:00:00")
		self.assertIn("modified", f)
		self.assertEqual(f["modified"][0], ">=")

	def test_get_modified_filter_empty(self):
		self.assertEqual(pull_service.get_modified_filter(None), {})

	def test_get_modified_filter_invalid_raises(self):
		with self.assertRaises(frappe.ValidationError):
			pull_service.get_modified_filter("not-a-date")

	def test_branch_context(self):
		context = pull_service.get_branch_context(BRANCH)
		self.assertEqual(context["branch"], BRANCH)
		self.assertTrue(context["company"])
		self.assertTrue(context["warehouse"])

	def test_pull_items_returns_records_and_total(self):
		records, total = pull_service.pull_items(page=1, page_size=5)
		self.assertIsInstance(records, list)
		self.assertGreater(total, 0)
		if records:
			self.assertIn("item_code", records[0])
			self.assertIn("modified", records[0])

	def test_fetch_items_for_pos_enriches_rows(self):
		items, total, context = pull_service.fetch_items_for_pos(branch=BRANCH, page=1, page_size=5)
		self.assertGreater(total, 0)
		self.assertEqual(context["branch"], BRANCH)
		if items:
			row = items[0]
			self.assertIn("barcodes", row)
			self.assertIn("item_prices", row)
			self.assertEqual(row["branch"], BRANCH)

	def test_pull_item_prices(self):
		records, total = pull_service.pull_item_prices(page=1, page_size=5)
		self.assertGreater(total, 0)

	def test_pull_stock_for_branch(self):
		stock, total, warehouse = pull_service.pull_stock(branch=BRANCH, page=1, page_size=5)
		self.assertIsInstance(stock, list)
		self.assertTrue(warehouse)

	def test_pull_system_settings_bundle(self):
		settings = pull_service.pull_system_settings(branch=BRANCH)
		for key in ("branches", "pos_devices", "tax_templates", "employees", "payment_methods", "warehouses"):
			self.assertIn(key, settings)

	def test_full_sync_structure(self):
		result = pull_service.full_sync(branch=BRANCH, page=1, page_size=5)
		self.assertEqual(result["sync_type"], "full")
		self.assertEqual(result["branch"], BRANCH)
		for key in (
			"items",
			"prices",
			"customers",
			"promotions",
			"discounts",
			"stock",
			"system_settings",
			"totals",
		):
			self.assertIn(key, result)
		self.assertIn("items", result["totals"])
