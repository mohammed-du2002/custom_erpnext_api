# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Regression tests for the middleware security hardening (SEC-01 .. SEC-11).

These are fast, hermetic unit tests that exercise the security primitives
directly with mocking, so they run under ``bench run-tests`` without needing a
live HTTP server. End-to-end HTTP coverage lives in
``custom_erpnext/setup/integration_tests.py``.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from custom_erpnext.api import auth, validators
from custom_erpnext.api.v1 import pull
from custom_erpnext.services import pull_service

BPS = "custom_erpnext.services.branch_permission_service"


class FakeCache:
	"""Minimal in-memory stand-in for Frappe's Redis wrapper."""

	def __init__(self):
		self.store = {}
		self.ttls = {}

	def incrby(self, key, amount=1):
		value = int(self.store.get(key, 0)) + amount
		self.store[key] = value
		return value

	def expire(self, key, ttl):
		self.ttls[key] = ttl
		return True

	def get(self, key):
		return self.store.get(key)

	def set(self, key, value, nx=False, ex=None):
		if nx and key in self.store:
			return None
		self.store[key] = value
		if ex:
			self.ttls[key] = ex
		return True

	def delete(self, key):
		self.store.pop(key, None)
		return True


# --------------------------------------------------------------------------- #
# SEC-01 — role bypass no longer disables HMAC / rate limiting                 #
# --------------------------------------------------------------------------- #
class TestAuthRoleGating(FrappeTestCase):
	def test_guest_rejected(self):
		original = frappe.session.user
		frappe.session.user = "Guest"
		try:
			with self.assertRaises(frappe.AuthenticationError):
				auth.validate_middleware_access()
		finally:
			frappe.session.user = original

	def test_privileged_external_request_is_signed_and_throttled(self):
		"""A System Manager / Administrator token request must NOT bypass (SEC-01)."""
		with patch(f"{auth.__name__}._is_privileged_user", return_value=True), patch(
			f"{auth.__name__}._is_external_api_request", return_value=True
		), patch(
			f"{auth.__name__}.get_integration_settings",
			return_value=[{"auth_type": "API Key", "api_secret": "s", "rate_limit_per_minute": 60}],
		), patch(f"{auth.__name__}._check_rate_limit") as rate_limit, patch(
			f"{auth.__name__}._validate_request_signature"
		) as signature:
			auth.validate_middleware_access()

		rate_limit.assert_called_once()
		signature.assert_called_once()

	def test_privileged_internal_request_bypasses(self):
		"""Desk/server-side privileged callers (no Authorization header) still bypass."""
		with patch(f"{auth.__name__}._is_privileged_user", return_value=True), patch(
			f"{auth.__name__}._is_external_api_request", return_value=False
		), patch(
			f"{auth.__name__}.get_integration_settings", return_value=[{"name": "x"}]
		), patch(f"{auth.__name__}._check_rate_limit") as rate_limit, patch(
			f"{auth.__name__}._validate_request_signature"
		) as signature:
			auth.validate_middleware_access()

		rate_limit.assert_not_called()
		signature.assert_not_called()


# --------------------------------------------------------------------------- #
# SEC-03 — branch scope resolution for optional-branch reads                   #
# --------------------------------------------------------------------------- #
class TestBranchScopeResolution(FrappeTestCase):
	def test_explicit_branch_is_validated_and_returned(self):
		with patch(f"{pull.__name__}.validate_branch_access") as vba:
			scope, deny = pull._resolve_branch_scope("BR1")
		vba.assert_called_once_with("BR1")
		self.assertEqual(scope, "BR1")
		self.assertFalse(deny)

	def test_bypass_role_is_unrestricted(self):
		with patch(f"{pull.__name__}.bypass_branch_restrictions", return_value=True):
			scope, deny = pull._resolve_branch_scope(None)
		self.assertIsNone(scope)
		self.assertFalse(deny)

	def test_restricted_user_scoped_to_allowed_branches(self):
		with patch(f"{pull.__name__}.bypass_branch_restrictions", return_value=False), patch(
			f"{pull.__name__}.get_user_branches", return_value=["BR1", "BR2"]
		):
			scope, deny = pull._resolve_branch_scope(None)
		self.assertEqual(scope, ["BR1", "BR2"])
		self.assertFalse(deny)

	def test_restricted_user_without_branches_is_denied(self):
		with patch(f"{pull.__name__}.bypass_branch_restrictions", return_value=False), patch(
			f"{pull.__name__}.get_user_branches", return_value=[]
		):
			scope, deny = pull._resolve_branch_scope(None)
		self.assertIsNone(scope)
		self.assertTrue(deny)

	def test_branch_clause_builds_in_filter_for_list(self):
		self.assertEqual(pull_service._branch_clause(["BR1", "BR2"]), ["in", ["BR1", "BR2"]])
		self.assertEqual(pull_service._branch_clause("BR1"), "BR1")


# --------------------------------------------------------------------------- #
# SEC-05 / SEC-06 — retry/replay-safe idempotency for write endpoints          #
# --------------------------------------------------------------------------- #
class TestIdempotentWrite(FrappeTestCase):
	def test_same_nonce_runs_once_and_replays_response(self):
		calls = {"n": 0}

		@auth.idempotent_write
		def handler(x=None):
			calls["n"] += 1
			return {"ok": True, "x": x, "call": calls["n"]}

		fake = FakeCache()
		with patch.object(frappe, "cache", fake), patch(
			f"{auth.__name__}._get_request_nonce", return_value="nonce-1"
		):
			first = handler(x=5)
			second = handler(x=5)

		self.assertEqual(calls["n"], 1, "side effect must execute only once")
		self.assertEqual(first, second, "replay must return the original response")
		self.assertEqual(second["call"], 1)

	def test_distinct_nonces_execute_independently(self):
		calls = {"n": 0}

		@auth.idempotent_write
		def handler():
			calls["n"] += 1
			return {"call": calls["n"]}

		fake = FakeCache()
		with patch.object(frappe, "cache", fake), patch(
			f"{auth.__name__}._get_request_nonce", side_effect=["nonce-a", "nonce-b"]
		):
			handler()
			handler()

		self.assertEqual(calls["n"], 2)

	def test_missing_nonce_does_not_cache(self):
		calls = {"n": 0}

		@auth.idempotent_write
		def handler():
			calls["n"] += 1
			return {"call": calls["n"]}

		fake = FakeCache()
		with patch.object(frappe, "cache", fake), patch(
			f"{auth.__name__}._get_request_nonce", return_value=None
		):
			handler()
			handler()

		self.assertEqual(calls["n"], 2, "without a nonce every call must run")

	def test_failed_call_is_not_cached(self):
		calls = {"n": 0}

		@auth.idempotent_write
		def handler():
			calls["n"] += 1
			if calls["n"] == 1:
				raise frappe.ValidationError("boom")
			return {"call": calls["n"]}

		fake = FakeCache()
		with patch.object(frappe, "cache", fake), patch(
			f"{auth.__name__}._get_request_nonce", return_value="nonce-x"
		):
			with self.assertRaises(frappe.ValidationError):
				handler()
			# A retry with the same nonce must re-execute, since the first failed.
			result = handler()

		self.assertEqual(result["call"], 2)


# --------------------------------------------------------------------------- #
# SEC-07 — atomic rate limiting                                                #
# --------------------------------------------------------------------------- #
class TestRateLimit(FrappeTestCase):
	def test_limit_enforced(self):
		fake = FakeCache()
		settings = {"rate_limit_per_minute": 3}
		with patch.object(frappe, "cache", fake):
			for _ in range(3):
				auth._check_rate_limit(settings)
			with self.assertRaises(frappe.RateLimitExceededError):
				auth._check_rate_limit(settings)

	def test_window_ttl_is_set(self):
		fake = FakeCache()
		with patch.object(frappe, "cache", fake):
			auth._check_rate_limit({"rate_limit_per_minute": 10})
		self.assertTrue(any(ttl == auth.RATE_LIMIT_WINDOW_TTL_SECONDS for ttl in fake.ttls.values()))

	def test_cache_failure_fails_open(self):
		class BrokenCache:
			def incrby(self, *a, **k):
				raise RuntimeError("redis down")

		with patch.object(frappe, "cache", BrokenCache()):
			# Must not raise — throttling degrades open rather than blocking sync.
			auth._check_rate_limit({"rate_limit_per_minute": 1})


# --------------------------------------------------------------------------- #
# SEC-10 — no branch existence disclosure to restricted callers                #
# --------------------------------------------------------------------------- #
class TestBranchAccessDisclosure(FrappeTestCase):
	def test_restricted_nonexistent_branch_is_permission_error(self):
		with patch("frappe.db.exists", return_value=False), patch(
			f"{BPS}.bypass_branch_restrictions", return_value=False
		), patch(f"{BPS}.user_has_branch_access", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				validators.validate_branch_access("GHOST", user="u@example.com")

	def test_restricted_forbidden_branch_is_permission_error(self):
		with patch("frappe.db.exists", return_value=True), patch(
			f"{BPS}.bypass_branch_restrictions", return_value=False
		), patch(f"{BPS}.user_has_branch_access", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				validators.validate_branch_access("BR-OTHER", user="u@example.com")

	def test_privileged_nonexistent_branch_is_validation_error(self):
		with patch("frappe.db.exists", return_value=False), patch(
			f"{BPS}.bypass_branch_restrictions", return_value=True
		):
			with self.assertRaises(frappe.ValidationError):
				validators.validate_branch_access("GHOST", user="Administrator")

	def test_allowed_branch_passes(self):
		with patch("frappe.db.exists", return_value=True), patch(
			f"{BPS}.bypass_branch_restrictions", return_value=False
		), patch(f"{BPS}.user_has_branch_access", return_value=True):
			validators.validate_branch_access("BR1", user="u@example.com")


# --------------------------------------------------------------------------- #
# Branch-scoped push/pull hardening                                            #
# --------------------------------------------------------------------------- #
class TestWarehouseAccessValidation(FrappeTestCase):
	def test_requires_branch_link_when_required(self):
		with patch("frappe.db.get_value", return_value=None):
			with self.assertRaises(frappe.ValidationError):
				validators.validate_warehouse_access("WH-1", require_branch=True)

	def test_rejects_cross_branch_warehouse(self):
		with patch(f"{BPS}.bypass_branch_restrictions", return_value=False), patch(
			f"{BPS}.user_has_branch_access", return_value=False
		), patch("frappe.db.get_value", return_value="BR2"):
			with self.assertRaises(frappe.PermissionError):
				validators.validate_warehouse_access("WH-1", user="u@example.com", require_branch=True)

	def test_branch_warehouse_mismatch_raises(self):
		with patch("frappe.db.get_value", return_value="BR2"):
			with self.assertRaises(frappe.ValidationError):
				validators.validate_branch_warehouse_consistency("BR1", "WH-1")


class TestPushEndpointBranchGuards(FrappeTestCase):
	def setUp(self):
		if getattr(frappe.local, "response", None) is None:
			frappe.local.response = frappe._dict()

	def test_update_stock_quantities_rejects_branch_warehouse_mismatch(self):
		from custom_erpnext.api.v1 import push

		with patch(f"{auth.__name__}.validate_middleware_access", return_value={}), patch(
			f"{auth.__name__}._get_request_nonce", return_value=None
		), patch(f"{push.__name__}.validate_branch_access"), patch(
			f"{push.__name__}.validate_branch_warehouse_consistency",
			side_effect=frappe.ValidationError("mismatch"),
		):
			resp = push.update_stock_quantities(
				stock_updates=[{"item_code": "ITEM-1", "qty": 1}],
				warehouse="WH-1",
				branch="BR1",
			)

		self.assertFalse(resp["success"])
		self.assertEqual(resp["errors"][0]["code"], "VALIDATION_ERROR")

	def test_update_pos_device_status_requires_branch_access(self):
		from custom_erpnext.api.v1 import push

		with patch(f"{auth.__name__}.validate_middleware_access", return_value={}), patch(
			f"{auth.__name__}._get_request_nonce", return_value=None
		), patch("frappe.db.get_value", return_value="BR-OTHER"), patch(
			f"{push.__name__}.validate_branch_access",
			side_effect=frappe.PermissionError("denied"),
		):
			resp = push.update_pos_device_status(device_id="DEV-1", is_online=1)

		self.assertFalse(resp["success"])
		self.assertEqual(resp["errors"][0]["code"], "PERMISSION_ERROR")


class TestPullCashierShiftScope(FrappeTestCase):
	def setUp(self):
		if getattr(frappe.local, "response", None) is None:
			frappe.local.response = frappe._dict()

	def test_omitted_branch_scopes_to_allowed_branches(self):
		with patch(f"{pull.__name__}._resolve_branch_scope", return_value=(["BR1"], False)), patch(
			f"{auth.__name__}.validate_middleware_access", return_value={}
		), patch(
			"custom_erpnext.services.cashier_shift_service.pull_cashier_shifts",
			return_value=([], 0),
		) as pull_shifts:
			resp = pull.pull_cashier_shifts()

		self.assertTrue(resp["success"])
		pull_shifts.assert_called_once()
		self.assertEqual(pull_shifts.call_args.kwargs["branch"], ["BR1"])

	def test_no_branch_access_returns_empty(self):
		with patch(f"{pull.__name__}._resolve_branch_scope", return_value=(None, True)), patch(
			f"{auth.__name__}.validate_middleware_access", return_value={}
		):
			resp = pull.pull_cashier_shifts()

		self.assertTrue(resp["success"])
		self.assertEqual(resp["data"]["shifts"], [])


# --------------------------------------------------------------------------- #
# SEC-11 — modified_from validation                                            #
# --------------------------------------------------------------------------- #
class TestModifiedFromValidation(FrappeTestCase):
	def test_empty_returns_no_filter(self):
		self.assertEqual(pull_service.get_modified_filter(None), {})
		self.assertEqual(pull_service.get_modified_filter(""), {})

	def test_valid_datetime_builds_filter(self):
		result = pull_service.get_modified_filter("2026-01-01 00:00:00")
		self.assertIn("modified", result)
		self.assertEqual(result["modified"][0], ">=")

	def test_invalid_values_raise_validation_error(self):
		for bad in ("garbage", "13/40/2026", "2026-13-99"):
			with self.assertRaises(frappe.ValidationError):
				pull_service.get_modified_filter(bad)


# --------------------------------------------------------------------------- #
# SEC-02 — ZATCA status must not leak invoices outside the caller's branches   #
# --------------------------------------------------------------------------- #
class TestZatcaStatusAuthorization(FrappeTestCase):
	def setUp(self):
		if getattr(frappe.local, "response", None) is None:
			frappe.local.response = frappe._dict()

	def test_denies_out_of_scope_invoice(self):
		with patch(f"{auth.__name__}.validate_middleware_access", return_value={}), patch(
			f"{pull.__name__}.bypass_branch_restrictions", return_value=False
		), patch(f"{pull.__name__}.user_has_branch_access", return_value=False), patch(
			"frappe.db.get_value", return_value=frappe._dict(name="SI-1", branch="BR-OTHER")
		):
			resp = pull.get_sales_invoice_zatca_status(sales_invoice="SI-1")
		self.assertFalse(resp["success"])
		self.assertEqual(resp["errors"][0]["code"], "PERMISSION_ERROR")

	def test_missing_invoice_is_indistinguishable_from_forbidden(self):
		"""SEC-10: a missing invoice yields the same 403 so ids cannot be enumerated."""
		with patch(f"{auth.__name__}.validate_middleware_access", return_value={}), patch(
			f"{pull.__name__}.bypass_branch_restrictions", return_value=False
		), patch(f"{pull.__name__}.user_has_branch_access", return_value=False), patch(
			"frappe.db.get_value", return_value=None
		):
			resp = pull.get_sales_invoice_zatca_status(sales_invoice="SI-NOPE")
		self.assertFalse(resp["success"])
		self.assertEqual(resp["errors"][0]["code"], "PERMISSION_ERROR")

	def test_allows_in_scope_invoice(self):
		with patch(f"{auth.__name__}.validate_middleware_access", return_value={}), patch(
			f"{pull.__name__}.bypass_branch_restrictions", return_value=False
		), patch(f"{pull.__name__}.user_has_branch_access", return_value=True), patch(
			"frappe.db.get_value", return_value=frappe._dict(name="SI-1", branch="BR1")
		), patch(
			"custom_erpnext.integrations.zatca.utils.get_zatca_payload_for_invoice",
			return_value={"qr": "x"},
		):
			resp = pull.get_sales_invoice_zatca_status(sales_invoice="SI-1")
		self.assertTrue(resp["success"])


# --------------------------------------------------------------------------- #
# SEC-09 — write-bearing / mutating endpoints are POST-only                     #
# --------------------------------------------------------------------------- #
class TestWhitelistMethods(FrappeTestCase):
	def test_full_sync_is_post_only(self):
		methods = frappe.allowed_http_methods_for_whitelisted_func.get(pull.full_sync)
		self.assertEqual(methods, ["POST"], "full_sync writes a checkpoint and must not allow GET")

	def test_read_endpoint_still_allows_get(self):
		methods = frappe.allowed_http_methods_for_whitelisted_func.get(pull.pull_items)
		self.assertIn("GET", methods)
		self.assertIn("POST", methods)
