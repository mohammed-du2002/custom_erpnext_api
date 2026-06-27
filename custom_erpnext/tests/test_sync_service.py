# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from custom_erpnext.services import pull_service
from custom_erpnext.services.sync_service import (
	_post_webhook,
	_touch_urgent_sync_config,
	notify_middleware,
	trigger_urgent_sync_for_item,
)


class TestSyncService(IntegrationTestCase):
	def test_touch_urgent_sync_config_by_config_name(self):
		if not frappe.db.exists("Sync Configuration", "Urgent Item Changes"):
			return

		_touch_urgent_sync_config(config_name="Urgent Item Changes")
		last_sync = frappe.db.get_value("Sync Configuration", "Urgent Item Changes", "last_sync_time")
		self.assertTrue(last_sync)

	@patch("custom_erpnext.services.sync_service.make_post_request")
	def test_post_webhook_signs_payload(self, mock_post):
		mock_post.return_value = {"ok": True}
		frappe.flags.integration_request = MagicMock(status_code=202)

		integration = MagicMock()
		integration.webhook_url = "https://middleware.example.com/api/webhooks/erpnext"
		integration.get_password.side_effect = lambda field: {
			"api_key": "test-key",
			"api_secret": "test-secret",
		}[field]
		integration.request_timeout = 15

		status = _post_webhook(
			integration,
			{"event": "urgent_sync", "entity": "Item", "reference_name": "ITEM-1"},
			request_id="req-1",
		)
		self.assertEqual(status, 202)
		mock_post.assert_called_once()
		_, kwargs = mock_post.call_args
		headers = kwargs["headers"]
		self.assertEqual(headers["X-Request-ID"], "req-1")
		self.assertIn("X-Signature", headers)
		self.assertIn("Authorization", headers)
		body = kwargs["data"]
		self.assertIn("ITEM-1", body)

	@patch("custom_erpnext.services.sync_service._post_webhook")
	@patch("custom_erpnext.services.sync_service._get_active_integration")
	def test_notify_middleware_posts_when_webhook_configured(self, mock_get_integration, mock_post):
		integration = MagicMock()
		integration.name = "Laravel Middleware"
		integration.webhook_url = "https://middleware.example.com/api/webhooks/erpnext"
		mock_get_integration.return_value = integration
		mock_post.return_value = 200

		if not frappe.db.exists("Sync Configuration", "Urgent Item Changes"):
			return

		notify_middleware("Item", "TEST-ITEM", config_name="Urgent Item Changes", attempt=1)
		mock_post.assert_called_once()

	@patch("custom_erpnext.services.sync_service.trigger_urgent_sync")
	def test_trigger_urgent_sync_for_item_on_any_update(self, mock_trigger):
		doc = MagicMock()
		doc.name = "TEST-ITEM"
		trigger_urgent_sync_for_item(doc)
		mock_trigger.assert_called_once_with("Item", "TEST-ITEM", config_name="Urgent Item Changes")


class TestPullServiceFullSync(IntegrationTestCase):
	def test_full_sync_returns_expected_sections(self):
		if not frappe.db.exists("Company Branch", "BR1"):
			self.skipTest("BR1 branch not available")

		result = pull_service.full_sync(branch="BR1", page=1, page_size=5)
		for key in (
			"sync_type",
			"items",
			"prices",
			"customers",
			"promotions",
			"discounts",
			"stock",
			"system_settings",
			"totals",
		):
			self.assertIn(key, result)
		self.assertEqual(result["sync_type"], "full")

	def test_pull_system_settings_bundle(self):
		if not frappe.db.exists("Company Branch", "BR1"):
			self.skipTest("BR1 branch not available")

		settings = pull_service.pull_system_settings(branch="BR1")
		for key in ("branches", "pos_devices", "tax_templates", "employees", "payment_methods", "warehouses"):
			self.assertIn(key, settings)
