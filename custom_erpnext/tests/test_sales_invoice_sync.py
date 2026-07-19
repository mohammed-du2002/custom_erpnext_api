# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Unit tests for the Sales Invoice push/sync helpers (POS -> ERPNext)."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import cint

from custom_erpnext.services import sales_invoice_sync_service as sis

BRANCH = "BR1"


class TestSyncKeyResolution(IntegrationTestCase):
	def test_extract_sync_key_prefers_offline(self):
		self.assertEqual(sis._extract_sync_key({"offline_invoice_id": " OFF-1 "}), "OFF-1")
		self.assertEqual(sis._extract_sync_key({"online_invoice_id": "ON-1"}), "ON-1")
		self.assertEqual(sis._extract_sync_key({}), "")

	def test_resolve_sync_storage_offline(self):
		key, field = sis._resolve_sync_storage({"offline_invoice_id": "OFF-9"})
		self.assertEqual(key, "OFF-9")
		self.assertEqual(field, "offline_invoice_id")

	def test_resolve_sync_storage_online(self):
		key, field = sis._resolve_sync_storage({"online_invoice_id": "ON-9", "issued_online": 1})
		self.assertEqual(key, "ON-9")
		self.assertEqual(field, "online_invoice_id")

	def test_resolve_sync_storage_requires_key(self):
		with self.assertRaises(frappe.ValidationError):
			sis._resolve_sync_storage({})

	def test_find_invoice_by_sync_key_unknown(self):
		self.assertIsNone(sis.find_invoice_by_sync_key("DOES-NOT-EXIST-123"))

	def test_find_invoice_by_sync_key_blank(self):
		self.assertIsNone(sis.find_invoice_by_sync_key(""))


class TestPayloadShape(IntegrationTestCase):
	def test_has_full_invoice_payload_false_when_partial(self):
		self.assertFalse(sis._has_full_invoice_payload({"offline_invoice_id": "X"}))

	def test_has_full_invoice_payload_true(self):
		self.assertTrue(
			sis._has_full_invoice_payload(
				{
					"company": "tsc",
					"customer": "Walk-in Customer",
					"branch": BRANCH,
					"items": [{"item_code": "RET-RICE-5KG", "qty": 1}],
				}
			)
		)


class TestHeaderMapping(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_single_value("Global Defaults", "default_company")
		cls.has_branch = frappe.db.exists("Company Branch", BRANCH)

	def setUp(self):
		if not self.has_branch:
			self.skipTest(f"{BRANCH} not seeded")

	def test_offline_invoice_marks_pos_transaction(self):
		si = frappe.new_doc("Sales Invoice")
		sis._map_invoice_header(
			si,
			{
				"company": self.company,
				"customer": "Walk-in Customer",
				"branch": BRANCH,
				"offline_invoice_id": "OFF-POS-1",
				"is_pos": 0,
			},
		)
		self.assertEqual(cint(si.is_pos_transaction), 1)

	def test_explicit_non_pos_respected(self):
		si = frappe.new_doc("Sales Invoice")
		sis._map_invoice_header(
			si,
			{
				"company": self.company,
				"customer": "Walk-in Customer",
				"branch": BRANCH,
				"is_pos_transaction": 0,
				"online_invoice_id": "ON-1",
			},
		)
		self.assertEqual(cint(si.is_pos_transaction), 0)

	def test_resolve_warehouse_from_branch(self):
		expected = frappe.db.get_value("Company Branch", BRANCH, "warehouse")
		self.assertEqual(sis._resolve_warehouse({"branch": BRANCH}), expected)
