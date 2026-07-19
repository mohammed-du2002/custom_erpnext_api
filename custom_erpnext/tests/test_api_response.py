# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Unit tests for the standardized API response envelope and request validators."""

import frappe
from frappe.tests import IntegrationTestCase

from custom_erpnext.api import response, validators


class TestApiResponse(IntegrationTestCase):
	def test_success_envelope_shape(self):
		result = response.success(data={"id": 1}, meta={"page": 1}, message="ok")
		self.assertTrue(result["success"])
		self.assertEqual(result["data"], {"id": 1})
		self.assertEqual(result["errors"], [])
		self.assertEqual(result["meta"], {"page": 1})
		self.assertEqual(result["message"], "ok")

	def test_success_defaults(self):
		result = response.success()
		self.assertTrue(result["success"])
		self.assertEqual(result["data"], {})
		self.assertNotIn("meta", result)
		self.assertNotIn("message", result)

	def test_error_envelope_and_http_status(self):
		result = response.error("bad thing", code="X_ERR", http_status=422)
		self.assertFalse(result["success"])
		self.assertEqual(result["data"], {})
		self.assertEqual(result["errors"][0]["message"], "bad thing")
		self.assertEqual(result["errors"][0]["code"], "X_ERR")
		self.assertEqual(frappe.local.response.get("http_status_code"), 422)

	def test_paginated_meta_total_pages(self):
		meta = response.paginated_meta(page=2, page_size=10, total=25)
		self.assertEqual(meta["page"], 2)
		self.assertEqual(meta["page_size"], 10)
		self.assertEqual(meta["total"], 25)
		self.assertEqual(meta["total_pages"], 3)

	def test_paginated_meta_zero_page_size(self):
		meta = response.paginated_meta(page=1, page_size=0, total=5)
		self.assertEqual(meta["total_pages"], 0)


class TestApiValidators(IntegrationTestCase):
	def test_parse_json_field_passthrough(self):
		self.assertEqual(validators.parse_json_field({"a": 1}), {"a": 1})
		self.assertEqual(validators.parse_json_field([1, 2]), [1, 2])
		self.assertIsNone(validators.parse_json_field(None))

	def test_parse_json_field_string(self):
		self.assertEqual(validators.parse_json_field('{"a": 1}'), {"a": 1})

	def test_parse_json_field_invalid_raises(self):
		with self.assertRaises(frappe.ValidationError):
			validators.parse_json_field("{not-json", fieldname="body")

	def test_validate_pagination_defaults(self):
		page, page_size = validators.validate_pagination()
		self.assertEqual(page, 1)
		self.assertEqual(page_size, 100)

	def test_validate_pagination_caps_page_size(self):
		with self.assertRaises(frappe.ValidationError):
			validators.validate_pagination(page=1, page_size=99999)

	def test_validate_pagination_rejects_zero_page(self):
		with self.assertRaises(frappe.ValidationError):
			validators.validate_pagination(page=0, page_size=10)

	def test_validate_required_fields_missing(self):
		with self.assertRaises(frappe.ValidationError):
			validators.validate_required_fields({"a": 1}, ["a", "b"])

	def test_validate_required_fields_ok(self):
		validators.validate_required_fields({"a": 1, "b": 2}, ["a", "b"])

	def test_validate_branch_rejects_unknown(self):
		with self.assertRaises(frappe.ValidationError):
			validators.validate_branch("NON-EXISTENT-BRANCH")

	def test_validate_branch_accepts_seeded(self):
		if not frappe.db.exists("Company Branch", "BR1"):
			self.skipTest("BR1 not seeded")
		validators.validate_branch("BR1")

	def test_cint_safe(self):
		self.assertEqual(validators.cint_safe("7"), 7)
		self.assertEqual(validators.cint_safe(None, 3), 3)
		self.assertEqual(validators.cint_safe("abc", 9), 9)
