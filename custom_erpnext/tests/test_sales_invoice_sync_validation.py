# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from custom_erpnext.services.sales_invoice_sync_service import _validate_customer_and_address


class TestSalesInvoiceSyncValidation(FrappeTestCase):
	@classmethod
	def tearDownClass(cls):
		frappe.db.rollback()
		super().tearDownClass()

	def test_unknown_customer_raises_clear_error(self):
		with self.assertRaises(frappe.ValidationError) as ctx:
			_validate_customer_and_address(
				{
					"company": "tsc",
					"customer": "B2B Customer Name",
				}
			)
		self.assertIn("Customer B2B Customer Name not found", str(ctx.exception))

	def test_unknown_address_raises_clear_error(self):
		customer = frappe.get_all("Customer", pluck="name", limit=1)
		if not customer:
			self.skipTest("No customer")

		with self.assertRaises(frappe.ValidationError) as ctx:
			_validate_customer_and_address(
				{
					"company": "tsc",
					"customer": customer[0],
					"customer_address": "Customer Address Name",
				}
			)
		self.assertIn("Customer Address Customer Address Name not found", str(ctx.exception))
