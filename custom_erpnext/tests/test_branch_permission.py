# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Unit tests for branch isolation / permission logic."""

import frappe
from frappe.tests import IntegrationTestCase

from custom_erpnext.services import branch_permission_service as bps

CASHIER_BR1 = "cashier.br1@retail.local"
CASHIER_BR2 = "cashier.br2@retail.local"
MANAGER = "manager.retail@retail.local"


class TestBranchBypass(IntegrationTestCase):
	def test_administrator_bypasses(self):
		self.assertTrue(bps.bypass_branch_restrictions("Administrator"))

	def test_cashier_does_not_bypass(self):
		if not frappe.db.exists("User", CASHIER_BR1):
			self.skipTest("cashier user not seeded")
		self.assertFalse(bps.bypass_branch_restrictions(CASHIER_BR1))

	def test_admin_query_conditions_empty(self):
		self.assertEqual(bps.get_permission_query_conditions("Administrator", "Sales Invoice"), "")


class TestCashierBranchScope(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.has_users = frappe.db.exists("User", CASHIER_BR1) and frappe.db.exists("User", CASHIER_BR2)

	def setUp(self):
		if not self.has_users:
			self.skipTest("retail cashier users not seeded")

	def test_cashier_branches_scoped_to_own_branch(self):
		branches = bps.get_user_branches(CASHIER_BR1)
		self.assertIn("BR1", branches)
		self.assertNotIn("BR2", branches)

	def test_user_has_branch_access(self):
		self.assertTrue(bps.user_has_branch_access(CASHIER_BR1, "BR1"))
		self.assertFalse(bps.user_has_branch_access(CASHIER_BR1, "BR2"))

	def test_query_conditions_restrict_to_branch(self):
		cond = bps.get_permission_query_conditions(CASHIER_BR1, "Sales Invoice")
		self.assertIn("BR1", cond)
		self.assertNotIn("BR2", cond)

	def test_customer_conditions_allow_null_branch(self):
		# Customers with no branch are globally visible (walk-in style).
		cond = bps.get_permission_query_conditions(CASHIER_BR1, "Customer")
		self.assertIn("BR1", cond)
		self.assertIn("IFNULL", cond)

	def test_manager_sees_multiple_branches(self):
		if not frappe.db.exists("User", MANAGER):
			self.skipTest("manager user not seeded")
		branches = set(bps.get_user_branches(MANAGER))
		self.assertTrue({"BR1", "BR2", "BR3"}.issubset(branches))
