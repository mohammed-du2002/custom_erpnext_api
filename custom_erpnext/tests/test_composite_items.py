# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Regression tests for BUG-06: composite item explosion + validation (SRS §3.3.3)."""

import frappe
from frappe.tests.utils import FrappeTestCase

from custom_erpnext.services.item_service import (
	explode_composite_items,
	get_composite_components,
	validate_composite_item,
)


class TestCompositeItems(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
		cls.warehouse = frappe.db.get_value("Warehouse", {"is_group": 0}, "name")

	def tearDown(self):
		frappe.db.rollback()

	def _make_item(self, code, is_stock=1, is_composite=0, bundle=None):
		data = {
			"doctype": "Item",
			"item_code": code,
			"item_name": code,
			"item_group": self.item_group,
			"stock_uom": "Nos",
			"is_stock_item": is_stock,
		}
		if is_composite:
			data["is_composite"] = 1
			data["composite_bundle"] = bundle
		return frappe.get_doc(data).insert(ignore_permissions=True).name

	def test_validate_requires_bundle(self):
		doc = frappe._dict(is_composite=1, composite_bundle=None)
		with self.assertRaises(frappe.ValidationError):
			validate_composite_item(doc)

	def test_explosion_populates_packed_items(self):
		if not self.item_group:
			self.skipTest("No leaf Item Group available")

		c1 = self._make_item("ZZTEST-COMP-A")
		c2 = self._make_item("ZZTEST-COMP-B")
		host = self._make_item("ZZTEST-BUNDLE-HOST", is_stock=0)

		bundle = frappe.get_doc(
			{
				"doctype": "Product Bundle",
				"new_item_code": host,
				"items": [
					{"item_code": c1, "qty": 1},
					{"item_code": c2, "qty": 3},
				],
			}
		).insert(ignore_permissions=True)

		combo = self._make_item("ZZTEST-COMBO", is_stock=0, is_composite=1, bundle=bundle.name)

		components = get_composite_components(combo)
		self.assertEqual(len(components), 2)

		si = frappe.new_doc("Sales Invoice")
		si.set_warehouse = self.warehouse
		si.append("items", {"item_code": combo, "qty": 2})

		explode_composite_items(si)

		packed = {row.item_code: row.qty for row in si.get("packed_items")}
		self.assertEqual(packed.get(c1), 2)  # 1 per combo * 2
		self.assertEqual(packed.get(c2), 6)  # 3 per combo * 2
