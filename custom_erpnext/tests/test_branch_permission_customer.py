# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from custom_erpnext.services.branch_permission_service import has_branch_permission


class TestBranchPermissionCustomer(FrappeTestCase):
	@classmethod
	def tearDownClass(cls):
		frappe.db.rollback()
		super().tearDownClass()

	def test_customer_without_branch_allows_read_for_branch_user(self):
		customer = frappe.get_all("Customer", filters={"branch": ["is", "not set"]}, pluck="name", limit=1)
		if not customer:
			self.skipTest("No customer without branch")

		user = frappe.session.user
		doc = frappe.get_doc("Customer", customer[0])
		self.assertTrue(has_branch_permission(doc, ptype="read", user=user))

	def test_middleware_sync_bypasses_branch_permission(self):
		customer = frappe.get_all("Customer", pluck="name", limit=1)
		if not customer:
			self.skipTest("No customer")

		doc = frappe.get_doc("Customer", customer[0])
		frappe.local.middleware_sync = True
		try:
			self.assertTrue(has_branch_permission(doc, ptype="read", user="middleware@laravel.local"))
		finally:
			frappe.local.middleware_sync = False
