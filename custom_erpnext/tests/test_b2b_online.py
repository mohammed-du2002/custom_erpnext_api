# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Regression tests for BUG-11: B2B e-invoices must be issued online (SRS §7.3)."""

import frappe
from frappe.tests.utils import FrappeTestCase

from custom_erpnext.services.sales_invoice_service import validate_b2b_requires_online
from custom_erpnext.services.sales_invoice_sync_service import (
	_resolve_sync_storage,
	_validate_b2b_online_origin,
)


class TestB2BOnline(FrappeTestCase):
	def test_offline_b2b_rejected(self):
		doc = frappe._dict(e_invoice_type="B2B", offline_invoice_id="POS-OFF-1")
		with self.assertRaises(frappe.ValidationError):
			validate_b2b_requires_online(doc)

	def test_offline_b2c_allowed(self):
		# Must not raise — B2C simplified invoices are valid offline.
		validate_b2b_requires_online(
			frappe._dict(e_invoice_type="B2C", offline_invoice_id="POS-OFF-1")
		)

	def test_online_b2b_allowed(self):
		# No offline origin -> issued online -> allowed.
		validate_b2b_requires_online(frappe._dict(e_invoice_type="B2B", offline_invoice_id=None))

	def test_sync_payload_b2b_requires_issued_online(self):
		with self.assertRaises(frappe.ValidationError):
			_validate_b2b_online_origin(
				{"customer": "ZATCA Sandbox B2B", "issued_online": 0}
			)

	def test_sync_payload_b2b_online_storage_field(self):
		key, field = _resolve_sync_storage(
			{
				"offline_invoice_id": "POS-B2B-ONLINE-1",
				"issued_online": 1,
			}
		)
		self.assertEqual(key, "POS-B2B-ONLINE-1")
		self.assertEqual(field, "online_invoice_id")
