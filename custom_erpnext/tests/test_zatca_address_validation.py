# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from custom_erpnext.services.address_validation_service import (
	collect_zatca_address_issues,
	validate_zatca_customer_address,
)


class TestZatcaAddressValidation(FrappeTestCase):
	@classmethod
	def tearDownClass(cls):
		frappe.db.rollback()
		super().tearDownClass()

	def _make_address(self, **kwargs):
		doc = frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": kwargs.get("address_title", "Test ZATCA Address"),
				"address_type": "Billing",
				"address_line1": kwargs.get("address_line1", "King Fahd Road"),
				"city": kwargs.get("city", "Riyadh"),
				"country": kwargs.get("country", "Saudi Arabia"),
				"pincode": kwargs.get("pincode", "12345"),
				"custom_building_number": kwargs.get("custom_building_number", "1234"),
				"custom_area": kwargs.get("custom_area", "Al Olaya"),
			}
		)
		doc.insert(ignore_permissions=True)
		return doc

	def test_valid_saudi_address(self):
		address = self._make_address()
		result = validate_zatca_customer_address(address.name)
		self.assertTrue(result["valid"])
		self.assertEqual(result["issues"], [])

	def test_missing_building_number(self):
		address = self._make_address(custom_building_number="")
		issues = collect_zatca_address_issues(address)
		self.assertTrue(any("building number" in issue.lower() for issue in issues))

	def test_invalid_postal_code(self):
		address = self._make_address(pincode="123")
		issues = collect_zatca_address_issues(address)
		self.assertTrue(any("postal code" in issue.lower() for issue in issues))

	def test_missing_district(self):
		address = self._make_address(custom_area="")
		issues = collect_zatca_address_issues(address)
		self.assertTrue(any("district" in issue.lower() for issue in issues))

	def test_validate_api_shape(self):
		result = validate_zatca_customer_address(None)
		self.assertFalse(result["valid"])
		self.assertTrue(result["issues"])
