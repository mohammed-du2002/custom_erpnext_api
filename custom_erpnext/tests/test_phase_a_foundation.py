# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestPhaseAFoundation(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_single_value("Global Defaults", "default_company")
		if not cls.company:
			cls.company = frappe.get_all("Company", pluck="name", limit=1)[0]

		cls.cost_center = frappe.db.get_value(
			"Cost Center", {"company": cls.company, "is_group": 0}, "name"
		)
		cls.warehouse = frappe.db.get_value("Warehouse", {"company": cls.company, "is_group": 0}, "name")
		# A company name that cannot collide with any real company; used to drive
		# the cross-company validations without provisioning a second company
		# (full company creation is blocked here by ksa_compliance mandatory fields).
		cls.foreign_company = "ZZ-NONEXISTENT-COMPANY"

	@classmethod
	def tearDownClass(cls):
		frappe.db.rollback()
		super().tearDownClass()

	def test_company_branch_doctype_exists(self):
		self.assertTrue(frappe.db.exists("DocType", "Company Branch"))

	def test_branch_section_doctype_exists(self):
		self.assertTrue(frappe.db.exists("DocType", "Branch Section"))

	def test_company_custom_fields(self):
		meta = frappe.get_meta("Company")
		for fieldname in (
			"number_of_branches",
			"default_cost_center",
			"central_warehouse",
			"party_account_model",
		):
			self.assertTrue(meta.has_field(fieldname), msg=f"Missing Company.{fieldname}")

	def test_warehouse_custom_fields(self):
		meta = frappe.get_meta("Warehouse")
		for fieldname in ("branch", "retail_warehouse_type", "is_pos_warehouse", "bin_locations"):
			self.assertTrue(meta.has_field(fieldname), msg=f"Missing Warehouse.{fieldname}")

	def test_user_custom_fields(self):
		meta = frappe.get_meta("User")
		for fieldname in ("branch", "sections", "max_discount", "pos_access", "erp_access"):
			self.assertTrue(meta.has_field(fieldname), msg=f"Missing User.{fieldname}")

	def test_branch_code_is_uppercased(self):
		doc = frappe.get_doc(
			{
				"doctype": "Company Branch",
				"branch_code": " qa01 ",
				"branch_name": "QA Branch",
				"company": self.company,
			}
		)
		doc.validate_branch_code()
		self.assertEqual(doc.branch_code, "QA01")

	def test_branch_rejects_foreign_cost_center(self):
		# The cost center belongs to the real company, while the branch claims a
		# different company -> validate_company_links must reject the mismatch.
		self.assertTrue(self.cost_center, "primary company must have a leaf cost center")

		doc = frappe.get_doc(
			{
				"doctype": "Company Branch",
				"branch_code": "QAFCC",
				"branch_name": "QA Foreign CC",
				"company": self.foreign_company,
				"cost_center": self.cost_center,
			}
		)
		with self.assertRaises(frappe.ValidationError):
			doc.validate_company_links()

	def test_warehouse_rejects_branch_from_other_company(self):
		# Branch is active and belongs to the real company; the warehouse claims a
		# different company -> validate_warehouse_branch must reject it.
		branch = self._ensure_branch("QAWH1", "QA Warehouse Branch")

		warehouse = frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": "QA Wrong Branch WH",
				"company": self.foreign_company,
				"branch": branch,
			}
		)
		with self.assertRaises(frappe.ValidationError):
			from custom_erpnext.services.foundation_service import validate_warehouse_branch

			validate_warehouse_branch(warehouse)

	def test_user_rejects_invalid_discount(self):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": "qa.discount@test.local",
				"first_name": "QA",
				"max_discount": 150,
			}
		)
		with self.assertRaises(frappe.ValidationError):
			from custom_erpnext.services.foundation_service import validate_user_retail_fields

			validate_user_retail_fields(user)

	def test_branch_section_requires_active_branch(self):
		branch = self._ensure_branch("QASEC1", "QA Section Branch")
		frappe.db.set_value("Company Branch", branch, "is_active", 0, update_modified=False)

		section = frappe.get_doc(
			{
				"doctype": "Branch Section",
				"section_code": "QAFLOOR",
				"section_name": "Sales Floor",
				"branch": branch,
			}
		)
		with self.assertRaises(frappe.ValidationError):
			section.validate()

		frappe.db.set_value("Company Branch", branch, "is_active", 1, update_modified=False)

	def test_branch_permission_hooks_registered(self):
		from custom_erpnext.services.branch_permission_service import BRANCH_ISOLATED_DOCTYPES

		for doctype in ("Company Branch", "Branch Section", "Warehouse"):
			self.assertIn(doctype, BRANCH_ISOLATED_DOCTYPES)

	def _ensure_branch(self, code, name):
		if frappe.db.exists("Company Branch", code):
			return code

		doc = frappe.get_doc(
			{
				"doctype": "Company Branch",
				"branch_code": code,
				"branch_name": name,
				"company": self.company,
				"cost_center": self.cost_center,
				"is_active": 1,
			}
		)
		doc.insert(ignore_permissions=True)
		return code
