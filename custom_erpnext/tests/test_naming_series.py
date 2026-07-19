# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Unit tests for branch-scoped naming series resolution."""

import frappe
from frappe.tests import IntegrationTestCase

from custom_erpnext.services import naming_series_service as nss

BRANCH = "BR1"


class TestBranchNamingSeries(IntegrationTestCase):
	def test_resolve_sales_invoice_series(self):
		self.assertEqual(nss.resolve_branch_series("Sales Invoice", "BR1"), "SINV-BR1-.")

	def test_resolve_sales_invoice_return_series(self):
		self.assertEqual(
			nss.resolve_branch_series("Sales Invoice", "BR1", is_return=True), "SINV-RET-BR1-."
		)

	def test_resolve_cashier_movement_series(self):
		self.assertEqual(nss.resolve_branch_series("Cashier Movement", "BR1"), "CMV-BR1-.")

	def test_resolve_unknown_doctype_returns_none(self):
		self.assertIsNone(nss.resolve_branch_series("Sales Order", "BR1"))

	def test_resolve_without_branch_code_returns_none(self):
		self.assertIsNone(nss.resolve_branch_series("Sales Invoice", None))

	def test_get_branch_code_from_seeded_branch(self):
		if not frappe.db.exists("Company Branch", BRANCH):
			self.skipTest("BR1 not seeded")
		self.assertEqual(nss.get_branch_code(BRANCH), "BR1")

	def test_get_naming_series_for_branch(self):
		if not frappe.db.exists("Company Branch", BRANCH):
			self.skipTest("BR1 not seeded")
		self.assertEqual(nss.get_naming_series_for_branch("Sales Invoice", BRANCH), "SINV-BR1-.")

	def test_naming_series_registered_as_option(self):
		if not frappe.db.exists("Company Branch", BRANCH):
			self.skipTest("BR1 not seeded")
		options = frappe.get_meta("Sales Invoice").get_naming_series_options()
		self.assertIn("SINV-BR1-.", options)
