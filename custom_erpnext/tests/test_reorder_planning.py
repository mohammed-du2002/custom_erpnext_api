# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Regression tests for BUG-08: reorder supplier suggestion + transfer alternative."""

import frappe
from frappe.tests.utils import FrappeTestCase

from custom_erpnext.services.reorder_service import decide_reorder_action, get_default_supplier


class TestReorderPlanning(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_single_value("Global Defaults", "default_company") or (
			frappe.get_all("Company", pluck="name", limit=1) or [None]
		)[0]
		cls.item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
		cls.supplier_group = frappe.db.get_value("Supplier Group", {"is_group": 0}, "name")

	def tearDown(self):
		frappe.db.rollback()

	def test_decide_transfer_when_surplus(self):
		self.assertEqual(decide_reorder_action(10, {"available": 20}), "transfer")

	def test_decide_purchase_when_insufficient(self):
		self.assertEqual(decide_reorder_action(10, {"available": 5}), "purchase")

	def test_decide_purchase_when_no_source(self):
		self.assertEqual(decide_reorder_action(10, None), "purchase")

	def test_get_default_supplier_from_item_default(self):
		if not (self.company and self.item_group and self.supplier_group):
			self.skipTest("Missing company/item group/supplier group fixtures")

		supplier = frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": "ZZ Test Reorder Supplier",
				"supplier_group": self.supplier_group,
			}
		).insert(ignore_permissions=True)

		item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": "ZZTEST-REORDER-ITEM",
				"item_name": "ZZTEST-REORDER-ITEM",
				"item_group": self.item_group,
				"stock_uom": "Nos",
				"is_stock_item": 1,
				"item_defaults": [{"company": self.company, "default_supplier": supplier.name}],
			}
		).insert(ignore_permissions=True)

		self.assertEqual(get_default_supplier(item.name), supplier.name)

	def test_get_default_supplier_none_when_unset(self):
		self.assertIsNone(get_default_supplier("ZZ-NONEXISTENT-ITEM-XYZ"))
