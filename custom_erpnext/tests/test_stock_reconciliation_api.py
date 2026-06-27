# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Regression tests for BUG-15: reconcile_stock_quantities (was a misnamed no-op)."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from custom_erpnext.services.sales_invoice_sync_service import (
	reconcile_stock_quantities,
	update_stock_quantities,
)

WAREHOUSE = "ZZTEST-WH"
ITEM = "ZZTEST-REC-ITEM"


class TestStockReconciliationApi(FrappeTestCase):
	def test_variance_report_is_read_only(self):
		res = reconcile_stock_quantities([{"item_code": ITEM, "qty": 123456}], warehouse=WAREHOUSE)

		self.assertFalse(res["applied"])
		self.assertIsNone(res["stock_reconciliation"])
		self.assertEqual(res["count"], 1)

		row = res["items"][0]
		self.assertEqual(flt(row["variance"]), flt(123456) - flt(row["erp_qty"]))

	def test_legacy_alias_still_works(self):
		res = update_stock_quantities([{"item_code": ITEM, "qty": 1}], warehouse=WAREHOUSE)
		self.assertFalse(res["applied"])
		self.assertEqual(res["count"], 1)

	def test_apply_without_variance_creates_nothing(self):
		erp_qty = (
			frappe.db.get_value("Bin", {"item_code": ITEM, "warehouse": WAREHOUSE}, "actual_qty") or 0
		)
		res = reconcile_stock_quantities(
			[{"item_code": ITEM, "qty": erp_qty}], warehouse=WAREHOUSE, apply=True
		)
		self.assertTrue(res["applied"])
		self.assertIsNone(res["stock_reconciliation"])

	def test_requires_arguments(self):
		with self.assertRaises(frappe.ValidationError):
			reconcile_stock_quantities([], warehouse=WAREHOUSE)
		with self.assertRaises(frappe.ValidationError):
			reconcile_stock_quantities([{"item_code": ITEM, "qty": 1}], warehouse=None)

	def test_middleware_user_can_apply_reconciliation(self):
		if not frappe.db.exists("User", "middleware@laravel.local"):
			self.skipTest("Middleware user not configured")

		warehouse = frappe.db.get_value("Company Branch", "BR1", "warehouse") if frappe.db.exists(
			"Company Branch", "BR1"
		) else None
		item = frappe.get_all("Item", filters={"is_stock_item": 1, "disabled": 0}, pluck="name", limit=1)
		if not warehouse or not item:
			self.skipTest("Need branch warehouse and stock item")

		frappe.set_user("middleware@laravel.local")

		erp_qty = frappe.db.get_value("Bin", {"item_code": item[0], "warehouse": warehouse}, "actual_qty") or 0
		target_qty = flt(erp_qty) + 1

		res = reconcile_stock_quantities(
			[{"item_code": item[0], "qty": target_qty}],
			warehouse=warehouse,
			apply=True,
		)
		self.assertTrue(res["applied"])
		self.assertTrue(res["stock_reconciliation"])
		self.assertTrue(frappe.db.exists("Stock Reconciliation", res["stock_reconciliation"]))
