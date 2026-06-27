# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Regression tests for BUG-10: partial purchase prepayment allocation (SRS §4.6)."""

import frappe
from frappe.tests.utils import FrappeTestCase


class TestPurchasePrepayment(FrappeTestCase):
	def _doc(self, amount, allocated=None, status="Paid", allocated_to_invoice=None):
		doc = frappe.new_doc("Purchase Prepayment")
		doc.amount = amount
		doc.status = status
		if allocated is not None:
			doc.allocated_amount = allocated
		if allocated_to_invoice:
			doc.allocated_to_invoice = allocated_to_invoice
		return doc

	def test_partial_allocation(self):
		doc = self._doc(1000, allocated=400)
		doc.set_remaining_amount()
		self.assertEqual(doc.allocated_amount, 400)
		self.assertEqual(doc.remaining_amount, 600)
		self.assertEqual(doc.status, "Partially Allocated")

	def test_full_allocation(self):
		doc = self._doc(1000, allocated=1000)
		doc.set_remaining_amount()
		self.assertEqual(doc.remaining_amount, 0)
		self.assertEqual(doc.status, "Allocated")

	def test_legacy_full_allocation_by_status(self):
		doc = self._doc(1000, allocated=None, status="Allocated", allocated_to_invoice="PINV-LEGACY")
		doc.set_remaining_amount()
		self.assertEqual(doc.remaining_amount, 0)

	def test_zero_allocation_resets_status(self):
		doc = self._doc(1000, allocated=0, status="Allocated")
		doc.set_remaining_amount()
		self.assertEqual(doc.remaining_amount, 1000)
		self.assertEqual(doc.status, "Paid")

	def test_over_allocation_rejected(self):
		doc = self._doc(1000, allocated=1200)
		with self.assertRaises(frappe.ValidationError):
			doc.validate_allocated_amount()
