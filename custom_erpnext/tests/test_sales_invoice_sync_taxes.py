# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from custom_erpnext.services.sales_invoice_sync_service import (
	_apply_sales_taxes,
	_resolve_taxes_and_charges,
)


class TestSalesInvoiceSyncTaxes(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_single_value("Global Defaults", "default_company")
		if not cls.company:
			cls.company = frappe.get_all("Company", pluck="name", limit=1)[0]

	@classmethod
	def tearDownClass(cls):
		frappe.db.rollback()
		super().tearDownClass()

	def test_resolve_taxes_and_charges_from_company_default(self):
		si = frappe.new_doc("Sales Invoice")
		si.company = self.company
		template = _resolve_taxes_and_charges(si, {})
		if not template:
			self.skipTest("No Sales Taxes and Charges Template for test company")
		self.assertTrue(frappe.db.exists("Sales Taxes and Charges Template", template))

	def test_apply_sales_taxes_populates_tax_rows(self):
		customer = frappe.get_all("Customer", pluck="name", limit=1)
		item = frappe.get_all("Item", filters={"is_sales_item": 1, "disabled": 0}, pluck="name", limit=1)
		if not customer or not item:
			self.skipTest("Need customer and sales item")

		si = frappe.new_doc("Sales Invoice")
		si.company = self.company
		si.customer = customer[0]
		si.is_pos = 1
		si.append("items", {"item_code": item[0], "qty": 1, "rate": 100})

		data = {"company": self.company, "customer": customer[0]}
		try:
			_apply_sales_taxes(si, data)
		except frappe.ValidationError as err:
			if "No sales tax rows applied" in str(err):
				self.skipTest("No tax template configured")
			raise

		self.assertTrue(si.taxes)
		self.assertGreater(flt(si.total_taxes_and_charges), 0)

	def test_tax_exempt_invoice_skips_tax_rows(self):
		"""BUG-09: zero-rated/exempt sales must sync without a tax template."""
		customer = frappe.get_all("Customer", pluck="name", limit=1)
		item = frappe.get_all("Item", filters={"is_sales_item": 1, "disabled": 0}, pluck="name", limit=1)
		if not customer or not item:
			self.skipTest("Need customer and sales item")

		si = frappe.new_doc("Sales Invoice")
		si.company = self.company
		si.customer = customer[0]
		si.is_pos = 1
		si.append("items", {"item_code": item[0], "qty": 1, "rate": 100})

		data = {"company": self.company, "customer": customer[0], "tax_exempt": 1}
		# Must not raise even when no default tax template exists.
		_apply_sales_taxes(si, data)

		self.assertFalse(si.get("taxes"))
		self.assertEqual(flt(si.total_taxes_and_charges), 0)
		self.assertGreater(flt(si.net_total), 0)
