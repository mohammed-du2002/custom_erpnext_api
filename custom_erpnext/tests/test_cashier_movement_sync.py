# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import uuid

import frappe
from frappe.tests.utils import FrappeTestCase

from custom_erpnext.services.cashier_movement_sync_service import (
	create_or_update_cashier_movement,
	sync_cashier_movements,
)


class TestCashierMovementSync(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_value("Company Branch", "BR1", "company") or frappe.db.get_single_value(
			"Global Defaults", "default_company"
		)
		cls.branch = "BR1" if frappe.db.exists("Company Branch", "BR1") else None
		cls.device = "TEST-POS-BR1" if frappe.db.exists("POS Device", "TEST-POS-BR1") else None
		cls.cashier = cls._resolve_cashier()

	@classmethod
	def tearDownClass(cls):
		frappe.db.rollback()
		super().tearDownClass()

	@classmethod
	def _resolve_cashier(cls):
		for user in ("cashier.br1@retail.local", "middleware@laravel.local", "Administrator"):
			if frappe.db.exists("User", user):
				if not frappe.db.get_value("User", user, "pos_access"):
					frappe.db.set_value("User", user, "pos_access", 1, update_modified=False)
				return user
		return None

	def _base_payload(self, suffix, movement_type, **extra):
		if not all([self.branch, self.device, self.cashier, self.company]):
			self.skipTest("Retail test fixtures not available")

		payload = {
			"offline_movement_id": f"CMV-TEST-{suffix}",
			"movement_type": movement_type,
			"movement_datetime": str(frappe.utils.now_datetime()),
			"company": self.company,
			"branch": self.branch,
			"pos_device": self.device,
			"cashier": self.cashier,
			"offline_shift_id": f"SHIFT-TEST-{suffix}",
			"shift_id": f"SHIFT-ID-{suffix}",
		}
		payload.update(extra)
		return payload

	def test_shift_open_cash_in_close_flow(self):
		suffix = uuid.uuid4().hex[:8]
		frappe.set_user("Administrator")

		open_result = create_or_update_cashier_movement(
			self._base_payload(suffix, "Shift Open", opening_balance=500)
		)
		self.assertFalse(open_result["idempotent"])
		self.assertTrue(frappe.db.exists("POS Cashier Shift", open_result["pos_cashier_shift"]))

		cash_in = create_or_update_cashier_movement(
			self._base_payload(
				suffix + "-IN",
				"Cash In",
				offline_shift_id=f"SHIFT-TEST-{suffix}",
				shift_id=f"SHIFT-ID-{suffix}",
				amount=100,
				reason="Test cash in",
			)
		)
		self.assertEqual(cash_in["status"], "success")

		close_result = create_or_update_cashier_movement(
			self._base_payload(
				suffix + "-CLOSE",
				"Shift Close",
				offline_shift_id=f"SHIFT-TEST-{suffix}",
				shift_id=f"SHIFT-ID-{suffix}",
				closing_balance=600,
			)
		)
		self.assertEqual(close_result["status"], "success")
		shift = frappe.get_doc("POS Cashier Shift", close_result["pos_cashier_shift"])
		self.assertEqual(shift.status, "Closed")
		self.assertEqual(flt(shift.expected_cash), 600)
		self.assertEqual(flt(shift.variance), 0)

	def test_idempotent_replay(self):
		suffix = uuid.uuid4().hex[:8]
		frappe.set_user("Administrator")
		payload = self._base_payload(suffix, "Shift Open", opening_balance=100)

		first = create_or_update_cashier_movement(payload)
		second = create_or_update_cashier_movement({"offline_movement_id": payload["offline_movement_id"]})

		self.assertFalse(first["idempotent"])
		self.assertTrue(second["idempotent"])
		self.assertEqual(first["cashier_movement"], second["cashier_movement"])

	def test_idempotent_retry_unknown_id_raises_clear_error(self):
		frappe.set_user("Administrator")
		with self.assertRaises(frappe.ValidationError) as ctx:
			create_or_update_cashier_movement({"offline_movement_id": "CMV-OPEN-UNKNOWN"})
		self.assertIn("not found", str(ctx.exception).lower())

	def test_shift_close_without_open_raises(self):
		if not all([self.branch, self.device, self.cashier, self.company]):
			self.skipTest("Retail test fixtures not available")

		frappe.set_user("Administrator")
		suffix = uuid.uuid4().hex[:8]
		with self.assertRaises(frappe.ValidationError):
			create_or_update_cashier_movement(
				self._base_payload(suffix, "Shift Close", closing_balance=100)
			)

	def test_cash_out_without_reason_raises(self):
		suffix = uuid.uuid4().hex[:8]
		frappe.set_user("Administrator")
		create_or_update_cashier_movement(self._base_payload(suffix, "Shift Open", opening_balance=100))

		with self.assertRaises(frappe.ValidationError):
			create_or_update_cashier_movement(
				self._base_payload(
					suffix + "-OUT",
					"Cash Out",
					offline_shift_id=f"SHIFT-TEST-{suffix}",
					shift_id=f"SHIFT-ID-{suffix}",
					amount=50,
				)
			)

	def test_duplicate_batch_ids_raise(self):
		if not all([self.branch, self.device, self.cashier, self.company]):
			self.skipTest("Retail test fixtures not available")

		suffix = uuid.uuid4().hex[:8]
		payload = self._base_payload(suffix, "Shift Open", opening_balance=100)
		with self.assertRaises(frappe.ValidationError):
			sync_cashier_movements([payload, payload])

	def test_future_datetime_rejected(self):
		suffix = uuid.uuid4().hex[:8]
		frappe.set_user("Administrator")
		payload = self._base_payload(suffix, "Shift Open", opening_balance=100)
		payload["movement_datetime"] = "2099-01-01 00:00:00"

		with self.assertRaises(frappe.ValidationError):
			create_or_update_cashier_movement(payload)


def flt(value):
	from frappe.utils import flt as _flt

	return _flt(value)
