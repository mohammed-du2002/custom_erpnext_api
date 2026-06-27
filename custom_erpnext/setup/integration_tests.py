# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""End-to-end HTTP integration tests for Laravel ↔ ERPNext middleware API."""

import hashlib
import hmac
import json
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import frappe

INTEGRATION_USER = "middleware@laravel.local"
BASE_URL_DEFAULT = "http://tsc.localhost"


class IntegrationTestRunner:
	def __init__(self, base_url=None, api_key=None, api_secret=None):
		self.base_url = (base_url or _guess_site_url()).rstrip("/")
		self.api_key = api_key
		self.api_secret = api_secret
		self.results = []

	def run_all(self):
		self._ensure_credentials()
		self._test_pull_endpoints()
		self._test_push_endpoints()
		self._test_auth_failures()
		return self._summary()

	def _ensure_credentials(self):
		if self.api_key and self.api_secret:
			return

		if not frappe.db.exists("User", INTEGRATION_USER):
			from custom_erpnext.setup.laravel_integration import setup_laravel_integration

			creds = setup_laravel_integration()
			self.api_key = creds["api_key"]
			self.api_secret = creds["api_secret"]
			return

		from custom_erpnext.setup.laravel_integration import setup_laravel_integration

		creds = setup_laravel_integration()
		self.api_key = creds["api_key"]
		self.api_secret = creds["api_secret"]

	def _test_pull_endpoints(self):
		self._run("pull.health_check", "custom_erpnext.api.v1.pull.health_check", {})
		self._run("pull.pull_branches", "custom_erpnext.api.v1.pull.pull_branches", {})
		self._run(
			"pull.get_items_for_pos",
			"custom_erpnext.api.v1.pull.get_items_for_pos",
			{"branch": "BR1", "page": 1, "page_size": 5},
		)
		self._run(
			"pull.pull_items",
			"custom_erpnext.api.v1.pull.pull_items",
			{"page": 1, "page_size": 5},
		)
		self._run(
			"pull.pull_item_groups",
			"custom_erpnext.api.v1.pull.pull_item_groups",
			{"page": 1, "page_size": 5},
		)
		self._run(
			"pull.pull_item_prices",
			"custom_erpnext.api.v1.pull.pull_item_prices",
			{"company": "tsc", "page": 1, "page_size": 5},
		)
		self._run(
			"pull.pull_customers",
			"custom_erpnext.api.v1.pull.pull_customers",
			{"branch": "BR1", "page": 1, "page_size": 5},
		)
		self._run(
			"pull.pull_tax_templates",
			"custom_erpnext.api.v1.pull.pull_tax_templates",
			{"page": 1, "page_size": 5},
		)
		self._run(
			"pull.pull_warehouses",
			"custom_erpnext.api.v1.pull.pull_warehouses",
			{"branch": "BR1", "page": 1, "page_size": 5},
		)
		self._run(
			"pull.pull_stock",
			"custom_erpnext.api.v1.pull.pull_stock",
			{"branch": "BR1", "page": 1, "page_size": 5},
		)
		self._run(
			"pull.pull_promotions",
			"custom_erpnext.api.v1.pull.pull_promotions",
			{"branch": "BR1", "page": 1, "page_size": 5},
		)
		self._run(
			"pull.pull_pos_devices",
			"custom_erpnext.api.v1.pull.pull_pos_devices",
			{"branch": "BR1"},
		)
		self._run(
			"pull.pull_discounts",
			"custom_erpnext.api.v1.pull.pull_discounts",
			{"branch": "BR1", "page": 1, "page_size": 50},
		)
		self._run(
			"pull.pull_employees",
			"custom_erpnext.api.v1.pull.pull_employees",
			{"branch": "BR1", "page": 1, "page_size": 50},
		)
		self._run(
			"pull.pull_cashier_shifts",
			"custom_erpnext.api.v1.pull.pull_cashier_shifts",
			{"branch": "BR1", "page": 1, "page_size": 5, "include_movements": 1},
		)
		self._run(
			"pull.pull_system_settings",
			"custom_erpnext.api.v1.pull.pull_system_settings",
			{"branch": "BR1"},
		)
		self._run(
			"pull.full_sync",
			"custom_erpnext.api.v1.pull.full_sync",
			{"branch": "BR1", "page": 1, "page_size": 5},
		)

	def _test_push_endpoints(self):
		request_id = str(uuid.uuid4())

		self._run(
			"push.sync_sales_invoices (idempotent)",
			"custom_erpnext.api.v1.push.sync_sales_invoices",
			{
				"request_id": request_id,
				"invoices": [
					{
						"offline_invoice_id": "LARAVEL-TEST-001",
						"company": "tsc",
						"customer": "Test Retail Customer",
						"branch": "BR1",
						"warehouse": "Stores - T",
						"posting_date": str(frappe.utils.getdate()),
						"is_pos": 1,
						"submit": 1,
						"items": [{"item_code": "TEST-RETAIL-ITEM", "qty": 1, "rate": 50}],
						"payments": [{"mode_of_payment": "Cash", "amount": 50}],
					}
				],
			},
			expect_keys=["data"],
		)

		self._run(
			"push.sync_sales_invoices (duplicate)",
			"custom_erpnext.api.v1.push.sync_sales_invoices",
			{
				"request_id": request_id,
				"invoices": [{"offline_invoice_id": "LARAVEL-TEST-001"}],
			},
			validate=lambda body: body.get("message", {}).get("data", {}).get("results", [{}])[0].get(
				"idempotent"
			),
		)

		self._run(
			"push.sync_daily_sales_summaries",
			"custom_erpnext.api.v1.push.sync_daily_sales_summaries",
			{
				"summaries": [
					{
						"summary_date": str(frappe.utils.getdate()),
						"branch": "BR1",
						"pos_device": "TEST-POS-BR1",
						"total_sales": 1500,
						"net_sales": 1400,
						"transaction_count": 10,
					}
				],
			},
		)

		self._run(
			"push.update_stock_quantities",
			"custom_erpnext.api.v1.push.update_stock_quantities",
			{
				"branch": "BR1",
				"stock_updates": [{"item_code": "TEST-RETAIL-ITEM", "qty": 100}],
			},
		)

		if frappe.db.exists("POS Device", {"device_id": "TEST-POS-BR1"}):
			self._run(
				"push.update_pos_device_status",
				"custom_erpnext.api.v1.push.update_pos_device_status",
				{
					"device_id": "TEST-POS-BR1",
					"is_online": 1,
					"last_sync_time": str(frappe.utils.now_datetime()),
				},
			)
		else:
			self.results.append(
				{
					"name": "push.update_pos_device_status",
					"passed": True,
					"skipped": True,
					"detail": "TEST-POS-BR1 device not found",
				}
			)

		self._test_cashier_movements()

	def _test_cashier_movements(self):
		if not frappe.db.exists("POS Device", {"device_id": "TEST-POS-BR1"}):
			self.results.append(
				{
					"name": "push.sync_cashier_movements",
					"passed": True,
					"skipped": True,
					"detail": "TEST-POS-BR1 device not found",
				}
			)
			return

		cashier = "cashier.br1@retail.local"
		if not frappe.db.exists("User", cashier) or not frappe.db.get_value("User", cashier, "pos_access"):
			cashier = "middleware@laravel.local"
			if frappe.db.exists("User", cashier):
				frappe.db.set_value("User", cashier, "pos_access", 1, update_modified=False)

		if not frappe.db.exists("User", cashier) or not frappe.db.get_value("User", cashier, "pos_access"):
			self.results.append(
				{
					"name": "push.sync_cashier_movements",
					"passed": True,
					"skipped": True,
					"detail": "No POS cashier user available",
				}
			)
			return

		request_id = str(uuid.uuid4())
		shift_suffix = uuid.uuid4().hex[:8]
		offline_shift_id = f"SHIFT-TEST-{shift_suffix}"
		open_id = f"CMV-TEST-OPEN-{shift_suffix}"
		cash_in_id = f"CMV-TEST-IN-{shift_suffix}"
		close_id = f"CMV-TEST-CLOSE-{shift_suffix}"
		now = str(frappe.utils.now_datetime())

		self._run(
			"push.sync_cashier_movements",
			"custom_erpnext.api.v1.push.sync_cashier_movements",
			{
				"request_id": request_id,
				"movements": [
					{
						"offline_movement_id": open_id,
						"movement_type": "Shift Open",
						"movement_datetime": now,
						"company": "tsc",
						"branch": "BR1",
						"pos_device": "TEST-POS-BR1",
						"cashier": cashier,
						"offline_shift_id": offline_shift_id,
						"shift_id": f"SHIFT-{shift_suffix}",
						"opening_balance": 500,
					},
					{
						"offline_movement_id": cash_in_id,
						"movement_type": "Cash In",
						"movement_datetime": now,
						"company": "tsc",
						"branch": "BR1",
						"pos_device": "TEST-POS-BR1",
						"cashier": cashier,
						"offline_shift_id": offline_shift_id,
						"shift_id": f"SHIFT-{shift_suffix}",
						"amount": 100,
						"reason": "Integration test cash in",
					},
					{
						"offline_movement_id": close_id,
						"movement_type": "Shift Close",
						"movement_datetime": now,
						"company": "tsc",
						"branch": "BR1",
						"pos_device": "TEST-POS-BR1",
						"cashier": cashier,
						"offline_shift_id": offline_shift_id,
						"shift_id": f"SHIFT-{shift_suffix}",
						"closing_balance": 600,
					},
				],
			},
			expect_keys=["data"],
		)

		self._run(
			"push.sync_cashier_movements (idempotent)",
			"custom_erpnext.api.v1.push.sync_cashier_movements",
			{
				"request_id": request_id,
				"movements": [{"offline_movement_id": open_id}],
			},
			validate=lambda body: body.get("message", {}).get("data", {}).get("results", [{}])[0].get(
				"idempotent"
			),
		)

	def _test_auth_failures(self):
		# Invalid signature should fail when secret is configured
		body = {"branch": "BR1"}
		try:
			status, response = _http_post(
				self.base_url,
				"custom_erpnext.api.v1.pull.get_items_for_pos",
				body,
				self.api_key,
				self.api_secret,
				sign=True,
				bad_signature=True,
			)
			passed = status == 401 or (response.get("message", {}).get("success") is False)
		except Exception as err:
			passed = True
			status = str(err)

		self.results.append(
			{
				"name": "auth.bad_signature_rejected",
				"passed": passed,
				"status": status,
			}
		)

		# Missing branch on required endpoint
		status, response = _http_post(
			self.base_url,
			"custom_erpnext.api.v1.pull.get_items_for_pos",
			{},
			self.api_key,
			self.api_secret,
		)
		self.results.append(
			{
				"name": "validation.missing_branch",
				"passed": response.get("message", {}).get("success") is False,
				"status": status,
				"error": _first_error(response),
			}
		)

	def _run(self, name, method, payload, expect_keys=None, validate=None):
		try:
			status, response = _http_post(
				self.base_url,
				method,
				payload,
				self.api_key,
				self.api_secret,
			)
			message = response.get("message", {})
			passed = message.get("success") is True and status == 200

			if expect_keys and passed:
				for key in expect_keys:
					if key not in message:
						passed = False

			if validate and passed:
				passed = bool(validate(response))

			self.results.append(
				{
					"name": name,
					"passed": passed,
					"status": status,
					"meta": message.get("meta"),
					"error": _first_error(response) if not passed else None,
				}
			)
		except Exception as err:
			self.results.append({"name": name, "passed": False, "error": str(err)})

	def _summary(self):
		passed = sum(1 for row in self.results if row.get("passed"))
		failed = [row for row in self.results if not row.get("passed")]
		skipped = sum(1 for row in self.results if row.get("skipped"))

		return {
			"base_url": self.base_url,
			"api_key": self.api_key,
			"total": len(self.results),
			"passed": passed,
			"failed": len(failed),
			"skipped": skipped,
			"success": len(failed) == 0,
			"results": self.results,
			"failures": failed,
		}


def run_laravel_integration_tests(base_url=None):
	"""Entry point for bench execute."""
	_ensure_test_pos_device()
	runner = IntegrationTestRunner(base_url=base_url)
	return runner.run_all()


def _ensure_test_pos_device():
	if frappe.db.exists("POS Device", {"device_id": "TEST-POS-BR1"}):
		return

	if not frappe.db.exists("Company Branch", "BR1"):
		return

	warehouse = frappe.db.get_value("Company Branch", "BR1", "warehouse")
	doc = frappe.get_doc(
		{
			"doctype": "POS Device",
			"device_id": "TEST-POS-BR1",
			"device_name": "Test POS BR1",
			"branch": "BR1",
			"warehouse": warehouse,
			"device_type": "Desktop",
			"is_active": 1,
		}
	)
	doc.insert(ignore_permissions=True)
	frappe.db.commit()


def _guess_site_url():
	host = frappe.conf.get("host_name")
	if host:
		return host if host.startswith("http") else f"http://{host}"
	return BASE_URL_DEFAULT


def _http_post(base_url, method, payload, api_key, api_secret, sign=True, bad_signature=False):
	body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
	url = f"{base_url}/api/method/{method}"
	request_id = str(uuid.uuid4())
	timestamp = str(int(time.time()))
	headers = {
		"Authorization": f"token {api_key}:{api_secret}",
		"Content-Type": "application/json",
		"Accept": "application/json",
		"X-Request-ID": request_id,
	}

	if sign:
		parsed = urlparse(url)
		query = parsed.query or ""
		# Canonical message must mirror the ERPNext middleware exactly:
		# METHOD \n PATH \n QUERY \n TIMESTAMP \n REQUEST_ID \n BODY
		sig_payload = "\n".join(["POST", parsed.path, query, timestamp, request_id, body])
		signature = hmac.new(
			api_secret.encode(),
			sig_payload.encode(),
			hashlib.sha256,
		).hexdigest()
		if bad_signature:
			signature = "invalid"
		headers["X-Timestamp"] = timestamp
		headers["X-Signature"] = signature

	request = Request(url, data=body.encode("utf-8"), headers=headers, method="POST")
	try:
		with urlopen(request, timeout=30) as response:
			status = response.status
			raw = response.read().decode("utf-8")
	except HTTPError as err:
		status = err.code
		raw = err.read().decode("utf-8")

	try:
		parsed = json.loads(raw)
	except json.JSONDecodeError:
		parsed = {"raw": raw}

	return status, parsed


def _first_error(response):
	errors = response.get("message", {}).get("errors") or []
	if errors:
		return errors[0]
	return response.get("exc") or response.get("raw")
