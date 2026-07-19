# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Sanity tests for the freshly seeded retail test environment.

These verify that the from-scratch reset produced the expected master data and
that the Laravel Middleware integration is configured. They are read-only and do
not create documents.
"""

import frappe
from frappe.tests import IntegrationTestCase

EXPECTED_BRANCHES = {"BR1", "BR2", "BR3"}
EXPECTED_ITEM_COUNT = 20
INTEGRATION_NAME = "Laravel Middleware"
MIDDLEWARE_USER = "middleware@laravel.local"


class TestRetailEnvironment(IntegrationTestCase):
	def test_single_company_configured(self):
		company = frappe.db.get_single_value("Global Defaults", "default_company")
		self.assertTrue(company, "A default company must be configured")
		self.assertEqual(frappe.db.get_value("Company", company, "default_currency"), "SAR")

	def test_setup_is_complete(self):
		self.assertTrue(frappe.is_setup_complete(), "ERPNext setup wizard must be complete")

	def test_three_active_branches_exist(self):
		branches = set(frappe.get_all("Company Branch", {"is_active": 1}, pluck="name"))
		self.assertTrue(EXPECTED_BRANCHES.issubset(branches))

	def test_each_branch_has_a_warehouse(self):
		for branch in EXPECTED_BRANCHES:
			warehouse = frappe.db.get_value("Company Branch", branch, "warehouse")
			self.assertTrue(warehouse, f"Branch {branch} must have a warehouse")
			self.assertEqual(frappe.db.get_value("Warehouse", warehouse, "branch"), branch)

	def test_retail_items_and_prices_seeded(self):
		items = frappe.get_all("Item", filters={"item_code": ["like", "RET-%"]}, pluck="name")
		self.assertGreaterEqual(len(items), EXPECTED_ITEM_COUNT)
		for item_code in items:
			self.assertTrue(
				frappe.db.exists("Item Price", {"item_code": item_code}),
				f"Item {item_code} must have at least one price",
			)

	def test_customers_seeded(self):
		self.assertTrue(frappe.db.exists("Customer", "Walk-in Customer"))
		self.assertGreaterEqual(frappe.db.count("Customer"), 5)

	def test_pos_profiles_and_devices_per_branch(self):
		for branch in EXPECTED_BRANCHES:
			self.assertTrue(
				frappe.db.exists("POS Profile", f"POS Profile - {branch}"),
				f"POS Profile for {branch} must exist",
			)
			self.assertTrue(
				frappe.db.exists("POS Device", {"branch": branch}),
				f"At least one POS Device for {branch} must exist",
			)

	def test_opening_stock_present(self):
		for branch in EXPECTED_BRANCHES:
			warehouse = frappe.db.get_value("Company Branch", branch, "warehouse")
			total_qty = frappe.db.get_value(
				"Bin",
				{"warehouse": warehouse, "item_code": "RET-RICE-5KG"},
				"actual_qty",
			)
			self.assertTrue(total_qty and total_qty > 0, f"{branch} must have opening stock")

	def test_modes_of_payment_have_zatca_code(self):
		for mop in ("Cash", "Credit Card"):
			self.assertTrue(frappe.db.exists("Mode of Payment", mop))
			self.assertTrue(
				frappe.db.get_value("Mode of Payment", mop, "custom_zatca_payment_means_code"),
				f"{mop} must have a ZATCA payment means code",
			)


class TestLaravelIntegrationConfig(IntegrationTestCase):
	def test_integration_settings_exist(self):
		self.assertTrue(frappe.db.exists("API Integration Settings", INTEGRATION_NAME))

	def test_endpoint_and_webhook_urls(self):
		doc = frappe.get_doc("API Integration Settings", INTEGRATION_NAME)
		self.assertEqual(doc.system, "Laravel Middleware")
		self.assertTrue(doc.is_active)
		self.assertEqual(doc.endpoint_url, "http://tsc.localhost")
		self.assertEqual(doc.webhook_url, "https://pos.src4it.com/api/webhook/erpnext")

	def test_middleware_user_exists_without_system_manager(self):
		self.assertTrue(frappe.db.exists("User", MIDDLEWARE_USER))
		roles = {r.role for r in frappe.get_doc("User", MIDDLEWARE_USER).roles}
		self.assertNotIn("System Manager", roles, "middleware user must not be System Manager")
		self.assertIn("Sales User", roles)

	def test_middleware_api_credentials_present(self):
		user = frappe.get_doc("User", MIDDLEWARE_USER)
		self.assertTrue(user.api_key)
		self.assertTrue(user.get_password("api_secret"))

	def test_sync_configurations_created(self):
		configs = frappe.get_all("Sync Configuration", pluck="name")
		for name in ("Pull Items", "Push Sales Invoices", "Urgent Item Changes", "Full Sync Day Open"):
			self.assertIn(name, configs)

	def test_sync_configuration_points_to_laravel_api(self):
		endpoint = frappe.db.get_value("Sync Configuration", "Pull Items", "api_endpoint")
		self.assertEqual(endpoint, "https://pos.src4it.com/api")
