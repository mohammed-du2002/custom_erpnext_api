# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import cint

from custom_erpnext.integrations.zatca.hooks import verify_zatca_integration
from custom_erpnext.services.sales_invoice_service import (
	apply_pos_transaction_flag,
	apply_retail_branch_defaults,
)


class TestP0SalesInvoiceRetail(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_single_value("Global Defaults", "default_company")
		if not cls.company:
			cls.company = frappe.get_all("Company", pluck="name", limit=1)[0]

		cls.branch = frappe.get_all(
			"Company Branch",
			filters={"company": cls.company, "is_active": 1},
			pluck="name",
			limit=1,
		)
		if not cls.branch:
			cls.branch = None
		else:
			cls.branch = cls.branch[0]

	@classmethod
	def tearDownClass(cls):
		frappe.db.rollback()
		super().tearDownClass()

	def test_is_pos_transaction_field_exists(self):
		self.assertTrue(frappe.get_meta("Sales Invoice").has_field("is_pos_transaction"))

	def test_apply_pos_transaction_flag_from_offline_id(self):
		doc = frappe.get_doc({"doctype": "Sales Invoice", "offline_invoice_id": "OFF-001"})
		apply_pos_transaction_flag(doc)
		self.assertEqual(cint(doc.is_pos_transaction), 1)

	def test_apply_pos_transaction_flag_respects_explicit_one(self):
		doc = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"is_pos_transaction": 1,
				"offline_invoice_id": "OFF-002",
			}
		)
		apply_pos_transaction_flag(doc)
		self.assertEqual(cint(doc.is_pos_transaction), 1)

	def test_apply_retail_branch_defaults_sets_cost_center(self):
		if not self.branch:
			self.skipTest("No active Company Branch in test site")

		expected_cc = frappe.db.get_value("Company Branch", self.branch, "cost_center")
		if not expected_cc:
			self.skipTest("Company Branch has no cost_center")

		doc = frappe.get_doc({"doctype": "Sales Invoice", "branch": self.branch})
		apply_retail_branch_defaults(doc)
		self.assertEqual(doc.cost_center, expected_cc)

	def test_verify_zatca_integration_fields(self):
		result = verify_zatca_integration()
		self.assertIn("sales_invoice_fields", result)
		self.assertTrue(result["sales_invoice_fields"].get("is_pos_transaction"))
		self.assertTrue(result["sales_invoice_fields"].get("zatca_status"))
		self.assertTrue(result["legacy_doctypes_removed"])

	def test_resolve_is_pos_transaction_from_sync_payload(self):
		from custom_erpnext.services.sales_invoice_sync_service import _map_invoice_header

		customer = frappe.get_all("Customer", pluck="name", limit=1)
		if not customer or not self.branch:
			self.skipTest("Need customer and branch")

		si = frappe.new_doc("Sales Invoice")
		_map_invoice_header(
			si,
			{
				"company": self.company,
				"customer": customer[0],
				"branch": self.branch,
				"offline_invoice_id": "OFF-SYNC-1",
				"is_pos": 0,
			},
		)
		self.assertEqual(cint(si.is_pos_transaction), 1)

		si2 = frappe.new_doc("Sales Invoice")
		_map_invoice_header(
			si2,
			{
				"company": self.company,
				"customer": customer[0],
				"branch": self.branch,
				"is_pos_transaction": 0,
				"offline_invoice_id": "OFF-SYNC-2",
			},
		)
		self.assertEqual(cint(si2.is_pos_transaction), 0)

	def test_resolve_warehouse_from_branch(self):
		if not self.branch:
			self.skipTest("No active Company Branch in test site")

		from custom_erpnext.services.sales_invoice_sync_service import _resolve_warehouse

		expected = frappe.db.get_value("Company Branch", self.branch, "warehouse")
		if not expected:
			self.skipTest("Company Branch has no warehouse")

		self.assertEqual(_resolve_warehouse({"branch": self.branch}), expected)

	def test_has_full_invoice_payload(self):
		from custom_erpnext.services.sales_invoice_sync_service import _has_full_invoice_payload

		self.assertFalse(_has_full_invoice_payload({"offline_invoice_id": "X"}))
		self.assertTrue(
			_has_full_invoice_payload(
				{
					"company": "tsc",
					"customer": "Test",
					"branch": "BR1",
					"items": [{"item_code": "ITEM", "qty": 1}],
				}
			)
		)
