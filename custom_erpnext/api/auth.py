# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import hashlib
import hmac
import json
import time
from functools import wraps

import frappe
from frappe import _

from custom_erpnext.api.response import error


INTEGRATION_SYSTEM = "Laravel Middleware"
RATE_LIMIT_CACHE_PREFIX = "middleware_api_rate"
SIGNATURE_TOLERANCE_SECONDS = 300


def get_integration_settings():
	rows = frappe.get_all(
		"API Integration Settings",
		filters={"system": INTEGRATION_SYSTEM, "is_active": 1},
		fields=["name"],
		limit=1,
	)
	if not rows:
		return []

	doc = frappe.get_doc("API Integration Settings", rows[0].name)
	return [
		{
			"name": doc.name,
			"auth_type": doc.auth_type,
			"rate_limit_per_minute": doc.rate_limit_per_minute,
			"request_timeout": doc.request_timeout,
			"api_key": doc.get_password("api_key"),
			"api_secret": doc.get_password("api_secret"),
		}
	]


def _get_request_id():
	request_id = frappe.form_dict.get("request_id")
	if request_id:
		return request_id
	try:
		return frappe.get_request_header("X-Request-ID")
	except RuntimeError:
		return None


def _get_request_body():
	try:
		return frappe.request.get_data(as_text=True) or ""
	except RuntimeError:
		return ""


def validate_middleware_access():
	if frappe.session.user in ("Administrator",) or "System Manager" in frappe.get_roles():
		return get_integration_settings()[0] if get_integration_settings() else {}

	if frappe.session.user == "Guest":
		frappe.throw(_("Authentication required"), frappe.AuthenticationError)

	settings_list = get_integration_settings()
	if not settings_list:
		frappe.throw(_("Laravel Middleware integration is not configured"), frappe.PermissionError)

	settings = settings_list[0]
	_check_rate_limit(settings)
	_validate_request_signature(settings)
	return settings


def _check_rate_limit(settings):
	limit = settings.get("rate_limit_per_minute") or 60
	cache_key = f"{RATE_LIMIT_CACHE_PREFIX}:{frappe.session.user}:{int(time.time() // 60)}"
	count = frappe.cache.get_value(cache_key) or 0
	if count >= limit:
		frappe.throw(_("Rate limit exceeded. Try again later."), frappe.RateLimitExceededError)
	frappe.cache.set_value(cache_key, count + 1, expires_in_sec=120)


def _validate_request_signature(settings):
	if settings.get("auth_type") != "API Key":
		return

	api_secret = settings.get("api_secret")
	if not api_secret:
		return

	try:
		timestamp = frappe.get_request_header("X-Timestamp")
		signature = frappe.get_request_header("X-Signature")
	except RuntimeError:
		return

	if not timestamp or not signature:
		return

	try:
		ts = int(timestamp)
	except (TypeError, ValueError):
		frappe.throw(_("Invalid timestamp header"))

	if abs(int(time.time()) - ts) > SIGNATURE_TOLERANCE_SECONDS:
		frappe.throw(_("Request timestamp expired"))

	payload = _get_request_body()
	message = f"{timestamp}.{payload}"
	expected = hmac.new(
		api_secret.encode("utf-8"),
		message.encode("utf-8"),
		hashlib.sha256,
	).hexdigest()

	if not hmac.compare_digest(expected, signature):
		frappe.throw(_("Invalid request signature"), frappe.AuthenticationError)


def middleware_api(fn):
	@wraps(fn)
	def wrapper(*args, **kwargs):
		request_id = _get_request_id()
		frappe.local.middleware_request_id = request_id

		try:
			settings = validate_middleware_access()
			frappe.local.middleware_integration = settings
			result = fn(*args, **kwargs)
			_log_request(fn.__name__, success=True)
			return result
		except frappe.RateLimitExceededError:
			_log_request(fn.__name__, success=False, message="Rate limit exceeded")
			return error(_("Rate limit exceeded"), code="RATE_LIMIT", http_status=429)
		except frappe.AuthenticationError as err:
			_log_request(fn.__name__, success=False, message=str(err))
			return error(str(err), code="AUTH_ERROR", http_status=401)
		except frappe.PermissionError as err:
			_log_request(fn.__name__, success=False, message=str(err))
			return error(str(err), code="PERMISSION_ERROR", http_status=403)
		except frappe.ValidationError as err:
			_log_request(fn.__name__, success=False, message=str(err))
			return error(str(err), code="VALIDATION_ERROR", http_status=422)
		except Exception as err:
			frappe.log_error(title=f"Middleware API: {fn.__name__}")
			_log_request(fn.__name__, success=False, message=str(err))
			return error(_("Internal server error"), code="INTERNAL_ERROR", http_status=500)

	return wrapper


def _log_request(method_name, success=True, message=None):
	frappe.logger("custom_erpnext.api").info(
		json.dumps(
			{
				"method": method_name,
				"user": frappe.session.user,
				"request_id": getattr(frappe.local, "middleware_request_id", None),
				"success": success,
				"message": message,
			}
		)
	)
