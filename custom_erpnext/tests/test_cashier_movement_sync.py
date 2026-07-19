# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Unit tests for cashier movement push validation (POS -> ERPNext)."""

from datetime import timedelta

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from custom_erpnext.services import cashier_movement_sync_service as cms


class TestMovementPayloadShape(IntegrationTestCase):
	def test_movement_types_defined(self):
		for mtype in ("Shift Open", "Shift Close", "Cash In", "Cash Out"):
			self.assertIn(mtype, cms.MOVEMENT_TYPES)

	def test_has_full_movement_payload_partial(self):
		self.assertFalse(cms._has_full_movement_payload({"movement_type": "Cash In"}))

	def test_has_full_movement_payload_complete(self):
		self.assertTrue(
			cms._has_full_movement_payload(
				{
					"movement_type": "Cash In",
					"company": "tsc",
					"branch": "BR1",
					"pos_device": "POS-BR1-01",
					"cashier": "cashier.br1@retail.local",
					"offline_shift_id": "SHIFT-1",
					"movement_datetime": "2026-01-01 09:00:00",
				}
			)
		)


class TestBatchValidation(IntegrationTestCase):
	def test_missing_offline_id_raises(self):
		with self.assertRaises(frappe.ValidationError):
			cms._validate_batch_ids([{"movement_type": "Cash In"}])

	def test_duplicate_offline_id_raises(self):
		with self.assertRaises(frappe.ValidationError):
			cms._validate_batch_ids(
				[
					{"offline_movement_id": "M-1"},
					{"offline_movement_id": "M-1"},
				]
			)

	def test_unique_offline_ids_ok(self):
		cms._validate_batch_ids(
			[
				{"offline_movement_id": "M-1"},
				{"offline_movement_id": "M-2"},
			]
		)


class TestMovementFieldValidation(IntegrationTestCase):
	def test_invalid_movement_type_raises(self):
		with self.assertRaises(frappe.ValidationError):
			cms._validate_movement_payload({"movement_type": "Teleport Cash"})

	def test_future_datetime_rejected(self):
		future = (now_datetime() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
		with self.assertRaises(frappe.ValidationError):
			cms._validate_movement_datetime(future)

	def test_past_datetime_accepted(self):
		past = (now_datetime() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
		cms._validate_movement_datetime(past)
