# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Unit tests for the middleware HMAC auth helpers."""

import hashlib
import hmac

import frappe
from frappe.tests import IntegrationTestCase

from custom_erpnext.api import auth

MIDDLEWARE_USER = "middleware@laravel.local"


class TestSignatureMessage(IntegrationTestCase):
	def test_message_is_canonical_and_ordered(self):
		# With no HTTP request context (server-side/test), method/path/query are blank.
		message = auth._build_signature_message("1700000000", "req-42", '{"a":1}')
		self.assertEqual(message, "\n\n\n1700000000\nreq-42\n{\"a\":1}")

	def test_message_binds_request_id_and_body(self):
		m1 = auth._build_signature_message("1700000000", "req-a", "body")
		m2 = auth._build_signature_message("1700000000", "req-b", "body")
		self.assertNotEqual(m1, m2)

	def test_signature_roundtrip(self):
		secret = "abc123"
		message = auth._build_signature_message("1700000000", "req-1", '{"x":1}')
		signature = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
		expected = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
		self.assertTrue(hmac.compare_digest(signature, expected))


class TestIntegrationSettingsLookup(IntegrationTestCase):
	def test_get_integration_settings_returns_active_config(self):
		settings = auth.get_integration_settings()
		if not settings:
			self.skipTest("Laravel Middleware integration not configured")
		row = settings[0]
		self.assertEqual(row["name"], "Laravel Middleware")
		self.assertEqual(row["auth_type"], "API Key")
		self.assertTrue(row["api_key"])
		self.assertTrue(row["api_secret"])

	def test_signing_secret_prefers_settings_for_internal_calls(self):
		settings = {"auth_type": "API Key", "api_secret": "settings-secret"}
		# No Authorization header in a server-side/test context -> internal caller.
		self.assertFalse(auth._is_external_api_request())
		self.assertEqual(auth._get_signing_secret(settings), "settings-secret")


class TestPrivilegeChecks(IntegrationTestCase):
	def test_administrator_is_privileged(self):
		self.assertTrue(auth._is_privileged_user())

	def test_middleware_user_is_not_privileged(self):
		frappe.set_user(MIDDLEWARE_USER)
		try:
			self.assertFalse(auth._is_privileged_user())
		finally:
			frappe.set_user("Administrator")
