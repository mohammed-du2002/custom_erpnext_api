# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Regression tests for HMAC signing enforcement (BUG-03) and canonical signature binding (SEC-04)."""

import hashlib
import hmac
import time
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from custom_erpnext.api import auth

SECRET = "unit-test-secret"
REQUEST_ID = "req-test-0001"


def _sign(timestamp, request_id, body):
	"""Mirror the server's canonical signing for tests."""
	message = auth._build_signature_message(timestamp, request_id, body)
	return hmac.new(SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()


def _headers(**values):
	def _get(name):
		return values.get(name)

	return _get


class TestMiddlewareSignature(FrappeTestCase):
	def _settings(self):
		return {"auth_type": "API Key", "api_secret": SECRET}

	@patch("frappe.get_request_header")
	def test_missing_signature_rejected(self, mock_header):
		"""Unsigned request with a configured secret must be rejected (BUG-03)."""
		mock_header.return_value = None
		with self.assertRaises(frappe.AuthenticationError):
			auth._validate_request_signature(self._settings())

	@patch("custom_erpnext.api.auth._is_external_api_request", return_value=False)
	@patch("frappe.get_request_header")
	def test_no_secret_skips_for_internal(self, mock_header, _mock_external):
		mock_header.return_value = None
		# No secret + internal caller -> signing cannot be enforced; must not raise.
		auth._validate_request_signature({"auth_type": "API Key", "api_secret": None})

	@patch("custom_erpnext.api.auth._is_external_api_request", return_value=False)
	@patch("frappe.get_request_header")
	def test_non_api_key_auth_skips_for_internal(self, mock_header, _mock_external):
		mock_header.return_value = None
		auth._validate_request_signature({"auth_type": "Basic", "api_secret": SECRET})

	@patch("custom_erpnext.api.auth._is_external_api_request", return_value=True)
	@patch("frappe.get_request_header")
	def test_unconfigured_signing_fails_closed_for_external(self, mock_header, _mock_external):
		"""SEC-08: an external token request must be rejected when signing is not configured."""
		mock_header.return_value = None
		with self.assertRaises(frappe.AuthenticationError):
			auth._validate_request_signature({"auth_type": "API Key", "api_secret": None})
		with self.assertRaises(frappe.AuthenticationError):
			auth._validate_request_signature({"auth_type": "Basic", "api_secret": SECRET})

	@patch("custom_erpnext.api.auth._get_request_body")
	@patch("frappe.get_request_header")
	def test_valid_signature_accepted(self, mock_header, mock_body):
		body = '{"event":"ping"}'
		ts = str(int(time.time()))
		mock_body.return_value = body
		sig = _sign(ts, REQUEST_ID, body)
		mock_header.side_effect = _headers(**{"X-Timestamp": ts, "X-Signature": sig, "X-Request-ID": REQUEST_ID})
		# Correctly signed request must pass without raising.
		auth._validate_request_signature(self._settings())

	@patch("custom_erpnext.api.auth._get_request_body")
	@patch("frappe.get_request_header")
	def test_missing_request_id_rejected(self, mock_header, mock_body):
		"""SEC-04: the request nonce is part of the signed message and is mandatory."""
		body = "{}"
		ts = str(int(time.time()))
		mock_body.return_value = body
		sig = _sign(ts, REQUEST_ID, body)
		# Valid timestamp + signature, but the X-Request-ID header is absent.
		mock_header.side_effect = _headers(**{"X-Timestamp": ts, "X-Signature": sig})
		with self.assertRaises(frappe.AuthenticationError):
			auth._validate_request_signature(self._settings())

	@patch("custom_erpnext.api.auth._get_request_body")
	@patch("frappe.get_request_header")
	def test_legacy_body_only_signature_rejected(self, mock_header, mock_body):
		"""SEC-04: the old `timestamp.body` signature scheme must no longer validate."""
		body = '{"event":"ping"}'
		ts = str(int(time.time()))
		mock_body.return_value = body
		legacy_sig = hmac.new(SECRET.encode(), f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()
		mock_header.side_effect = _headers(
			**{"X-Timestamp": ts, "X-Signature": legacy_sig, "X-Request-ID": REQUEST_ID}
		)
		with self.assertRaises(frappe.AuthenticationError):
			auth._validate_request_signature(self._settings())

	@patch("custom_erpnext.api.auth._get_request_body")
	@patch("frappe.get_request_header")
	def test_invalid_signature_rejected(self, mock_header, mock_body):
		body = '{"event":"ping"}'
		ts = str(int(time.time()))
		mock_body.return_value = body
		mock_header.side_effect = _headers(
			**{"X-Timestamp": ts, "X-Signature": "deadbeef", "X-Request-ID": REQUEST_ID}
		)
		with self.assertRaises(frappe.AuthenticationError):
			auth._validate_request_signature(self._settings())

	@patch("custom_erpnext.api.auth._get_request_body")
	@patch("frappe.get_request_header")
	def test_expired_timestamp_rejected(self, mock_header, mock_body):
		body = "{}"
		old_ts = str(int(time.time()) - 10_000)
		mock_body.return_value = body
		sig = _sign(old_ts, REQUEST_ID, body)
		mock_header.side_effect = _headers(
			**{"X-Timestamp": old_ts, "X-Signature": sig, "X-Request-ID": REQUEST_ID}
		)
		with self.assertRaises(frappe.ValidationError):
			auth._validate_request_signature(self._settings())

	@patch("custom_erpnext.api.auth._get_request_body")
	@patch("frappe.get_request_header")
	def test_signature_bound_to_request_id(self, mock_header, mock_body):
		"""SEC-04: a signature minted for one nonce must not validate for another."""
		body = '{"x":1}'
		ts = str(int(time.time()))
		mock_body.return_value = body
		sig_for_other = _sign(ts, "some-other-nonce", body)
		mock_header.side_effect = _headers(
			**{"X-Timestamp": ts, "X-Signature": sig_for_other, "X-Request-ID": REQUEST_ID}
		)
		with self.assertRaises(frappe.AuthenticationError):
			auth._validate_request_signature(self._settings())
