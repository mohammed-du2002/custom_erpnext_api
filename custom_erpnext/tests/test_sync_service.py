# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Unit tests for the urgent-sync webhook service (ERPNext -> Laravel)."""

import hashlib
import hmac
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from custom_erpnext.services import sync_service
from custom_erpnext.services.sync_service import (
	ENTITY_CONFIG,
	OPERATION_BY_METHOD,
	_post_webhook,
	_touch_urgent_sync_config,
	notify_middleware,
	trigger_urgent_sync_doc_event,
)


def _fake_integration(secret="webhook-secret", api_key="webhook-key"):
	integration = MagicMock()
	integration.name = "Laravel Middleware"
	integration.webhook_url = "https://pos.src4it.com/api/webhook/erpnext"
	integration.request_timeout = 15
	integration.get_password.side_effect = lambda field, raise_exception=True: {
		"webhook_api_key": api_key,
		"webhook_secret": secret,
	}.get(field)
	return integration


class TestWebhookSigning(IntegrationTestCase):
	@patch("custom_erpnext.services.sync_service.get_request_session")
	def test_post_webhook_signs_body_with_hmac_sha256(self, mock_session_factory):
		response = MagicMock(status_code=202)
		response.raise_for_status.return_value = None
		session = MagicMock()
		session.post.return_value = response
		mock_session_factory.return_value = session

		secret = "top-secret"
		integration = _fake_integration(secret=secret)
		payload = {"entity": "items", "erp_id": "RET-RICE-5KG", "operation": "update"}

		status = _post_webhook(integration, payload, request_id="req-1")

		self.assertEqual(status, 202)
		session.post.assert_called_once()
		_, kwargs = session.post.call_args
		headers, body = kwargs["headers"], kwargs["data"]

		self.assertEqual(headers["X-Request-ID"], "req-1")
		self.assertEqual(headers["X-Webhook-API-Key"], "webhook-key")
		self.assertNotIn("Authorization", headers)

		expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
		self.assertEqual(headers["X-Webhook-Signature"], expected)
		self.assertIn("RET-RICE-5KG", body)

	@patch("custom_erpnext.services.sync_service.get_request_session")
	def test_post_webhook_omits_signature_without_secret(self, mock_session_factory):
		response = MagicMock(status_code=202)
		response.raise_for_status.return_value = None
		session = MagicMock()
		session.post.return_value = response
		mock_session_factory.return_value = session

		integration = _fake_integration(secret=None)
		_post_webhook(integration, {"entity": "items", "erp_id": "X"}, request_id="req-2")

		_, kwargs = session.post.call_args
		self.assertNotIn("X-Webhook-Signature", kwargs["headers"])

	@patch("custom_erpnext.services.sync_service._post_webhook")
	@patch("custom_erpnext.services.sync_service._get_active_integration")
	def test_notify_middleware_builds_expected_payload(self, mock_get_integration, mock_post):
		mock_get_integration.return_value = _fake_integration()
		mock_post.return_value = 202

		notify_middleware("items", "RET-RICE-5KG", operation="update", config_name="Urgent Item Changes")

		mock_post.assert_called_once()
		sent_payload = mock_post.call_args.args[1]
		self.assertEqual(sent_payload["entity"], "items")
		self.assertEqual(sent_payload["erp_id"], "RET-RICE-5KG")
		self.assertEqual(sent_payload["operation"], "update")

	@patch("custom_erpnext.services.sync_service._get_active_integration")
	def test_notify_middleware_noop_without_webhook(self, mock_get_integration):
		integration = _fake_integration()
		integration.webhook_url = None
		mock_get_integration.return_value = integration
		# Should return quietly without attempting a POST.
		self.assertIsNone(notify_middleware("items", "X", operation="update"))


class TestDocEventMapping(IntegrationTestCase):
	def test_entity_config_covers_synced_doctypes(self):
		for doctype in ("Item", "Item Price", "Customer", "Promotion Rule", "User Discount Profile"):
			self.assertIn(doctype, ENTITY_CONFIG)
			self.assertIn("entity", ENTITY_CONFIG[doctype])
			self.assertIn("config_name", ENTITY_CONFIG[doctype])

	def test_operation_map(self):
		self.assertEqual(OPERATION_BY_METHOD["after_insert"], "create")
		self.assertEqual(OPERATION_BY_METHOD["on_update"], "update")
		self.assertEqual(OPERATION_BY_METHOD["on_trash"], "delete")

	@patch("custom_erpnext.services.sync_service.trigger_urgent_sync")
	def test_doc_event_maps_entity_and_operation(self, mock_trigger):
		doc = MagicMock()
		doc.doctype = "Item"
		doc.name = "RET-RICE-5KG"
		doc.flags = MagicMock(in_insert=False)
		doc.get.return_value = None

		trigger_urgent_sync_doc_event(doc, method="on_update")

		mock_trigger.assert_called_once_with(
			entity="items",
			erp_id="RET-RICE-5KG",
			operation="update",
			config_name="Urgent Item Changes",
			branch_id=None,
			company_id=None,
		)

	@patch("custom_erpnext.services.sync_service.trigger_urgent_sync")
	def test_doc_event_skips_update_during_insert(self, mock_trigger):
		doc = MagicMock()
		doc.doctype = "Item"
		doc.name = "RET-RICE-5KG"
		doc.flags = MagicMock(in_insert=True)
		doc.get.return_value = None

		trigger_urgent_sync_doc_event(doc, method="on_update")
		mock_trigger.assert_not_called()

	@patch("custom_erpnext.services.sync_service.trigger_urgent_sync")
	def test_doc_event_ignores_unmapped_doctype(self, mock_trigger):
		doc = MagicMock()
		doc.doctype = "Sales Order"
		doc.name = "SO-1"
		doc.flags = MagicMock(in_insert=False)
		trigger_urgent_sync_doc_event(doc, method="on_update")
		mock_trigger.assert_not_called()


class TestSyncConfigTouch(IntegrationTestCase):
	def test_touch_updates_last_sync_time(self):
		if not frappe.db.exists("Sync Configuration", "Urgent Item Changes"):
			self.skipTest("Urgent Item Changes config not present")

		frappe.db.set_value("Sync Configuration", "Urgent Item Changes", "last_sync_time", None)
		_touch_urgent_sync_config(config_name="Urgent Item Changes")
		self.assertTrue(
			frappe.db.get_value("Sync Configuration", "Urgent Item Changes", "last_sync_time")
		)
