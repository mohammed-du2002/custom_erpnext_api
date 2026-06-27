# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestSalesInvoiceDeskUI(FrappeTestCase):
	"""Retail desk form custom fields required for Amount Summary and E-Invoice panels."""

	RETAIL_PANEL_FIELDS = (
		"retail_summary_section",
		"retail_financial_summary",
		"retail_einvoice_section",
		"retail_einvoice_badge",
		"is_e_invoice",
		"e_invoice_type",
		"zatca_status",
		"pi_number",
		"zatca_reference",
		"zatca_sync_status",
	)

	DELIVERY_FIELDS = (
		"retail_delivery_section",
		"shipping_cost",
		"delivery_date",
		"driver",
		"delivery_status",
	)

	@classmethod
	def tearDownClass(cls):
		frappe.db.rollback()
		super().tearDownClass()

	def test_retail_panel_fields_exist(self):
		meta = frappe.get_meta("Sales Invoice")
		for fieldname in self.RETAIL_PANEL_FIELDS:
			self.assertTrue(
				meta.has_field(fieldname),
				f"Sales Invoice missing retail panel field: {fieldname}",
			)

	def test_amount_summary_section_label(self):
		meta = frappe.get_meta("Sales Invoice")
		self.assertEqual(meta.get_label("retail_summary_section"), "Amount Summary")

	def test_financial_summary_html_field(self):
		meta = frappe.get_meta("Sales Invoice")
		field = meta.get_field("retail_financial_summary")
		self.assertEqual(field.fieldtype, "HTML")
		self.assertIn("retail-financial-summary", field.options or "")

	def test_einvoice_badge_html_field(self):
		meta = frappe.get_meta("Sales Invoice")
		field = meta.get_field("retail_einvoice_badge")
		self.assertEqual(field.fieldtype, "HTML")
		self.assertIn("retail-einvoice-badge", field.options or "")

	def test_einvoice_section_label(self):
		meta = frappe.get_meta("Sales Invoice")
		self.assertEqual(meta.get_label("retail_einvoice_section"), "E-Invoicing")

	def test_delivery_fields_exist_for_hide_list(self):
		meta = frappe.get_meta("Sales Invoice")
		for fieldname in self.DELIVERY_FIELDS:
			self.assertTrue(
				meta.has_field(fieldname),
				f"Sales Invoice missing delivery field: {fieldname}",
			)

	def test_zatca_status_options(self):
		meta = frappe.get_meta("Sales Invoice")
		field = meta.get_field("zatca_status")
		for status in ("Pending", "Processing", "Cleared", "Reported", "Rejected"):
			self.assertIn(status, field.options)

	def test_e_invoice_type_options(self):
		meta = frappe.get_meta("Sales Invoice")
		field = meta.get_field("e_invoice_type")
		self.assertIn("B2B", field.options)
		self.assertIn("B2C", field.options)
