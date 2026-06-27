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
RATE_LIMIT_WINDOW_TTL_SECONDS = 90
SIGNATURE_TOLERANCE_SECONDS = 300

# Idempotency layer: a write request carrying the same X-Request-ID returns the
# stored response without re-running its side effect, making client retries and
# captured-request replays safe.
IDEMPOTENCY_CACHE_PREFIX = "middleware_api_idem"
IDEMPOTENCY_TTL_SECONDS = 24 * 60 * 60
IDEMPOTENCY_LOCK_SECONDS = 120
IDEMPOTENCY_WAIT_ATTEMPTS = 50
IDEMPOTENCY_WAIT_INTERVAL = 0.1


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


def _get_request_nonce():
	"""Transport-level request id (X-Request-ID header).

	Distinct from :func:`_get_request_id`, which prefers the body ``request_id``
	for application correlation. The header is the per-attempt nonce the client
	keeps stable across HTTP retries, so it is the correct key for replay/retry
	idempotency and for binding into the request signature.
	"""
	try:
		return frappe.get_request_header("X-Request-ID")
	except RuntimeError:
		return None


def _get_request_body():
	try:
		return frappe.request.get_data(as_text=True) or ""
	except RuntimeError:
		return ""


def _is_external_api_request():
	"""True when the call arrived over HTTP carrying an Authorization header.

	The Laravel middleware authenticates with ``Authorization: token key:secret``.
	Desk/session users authenticate via the ``sid`` cookie (no Authorization
	header) and server-side calls (bench execute, scheduled jobs) have no request
	context at all — both are treated as trusted internal callers.
	"""
	try:
		return bool(frappe.get_request_header("Authorization"))
	except RuntimeError:
		return False


def _is_privileged_user():
	return frappe.session.user == "Administrator" or "System Manager" in frappe.get_roles()


def validate_middleware_access():
	if frappe.session.user == "Guest":
		frappe.throw(_("Authentication required"), frappe.AuthenticationError)

	settings_list = get_integration_settings()

	# A privileged ROLE alone is NOT sufficient to skip signing/throttling. Only
	# genuine internal callers (desk session or server-side — i.e. no external API
	# token) may bypass. Every token-authenticated HTTP request is always rate
	# limited and signature-verified, even for System Manager / Administrator,
	# so the integration key cannot disable the HMAC layer by holding a role.
	if _is_privileged_user() and not _is_external_api_request():
		return settings_list[0] if settings_list else {}

	if not settings_list:
		frappe.throw(_("Laravel Middleware integration is not configured"), frappe.PermissionError)

	settings = settings_list[0]
	_check_rate_limit(settings)
	_validate_request_signature(settings)
	return settings


def _check_rate_limit(settings):
	limit = settings.get("rate_limit_per_minute") or 60
	window = int(time.time() // 60)
	cache_key = f"{RATE_LIMIT_CACHE_PREFIX}:{frappe.local.site}:{frappe.session.user}:{window}"

	# Atomic INCR removes the get/compare/set race (TOCTOU) that let concurrent
	# requests slip past the cap. Refresh the TTL each hit so the window-scoped
	# key always self-expires even if a prior process died before setting it.
	try:
		current = frappe.cache.incrby(cache_key, 1)
		frappe.cache.expire(cache_key, RATE_LIMIT_WINDOW_TTL_SECONDS)
	except Exception:
		# Cache backend unavailable — fail open on throttling rather than
		# blocking legitimate sync traffic.
		return

	if current and int(current) > limit:
		frappe.throw(_("Rate limit exceeded. Try again later."), frappe.RateLimitExceededError)


def _build_signature_message(timestamp, request_id, body):
	"""Canonical string the client and server both HMAC.

	Binds the HTTP method, path, query string and request nonce — not just the
	body — so a captured signature cannot be replayed against a different
	endpoint, with different query parameters, or with a forged request id.
	"""
	try:
		method = frappe.request.method or ""
		path = frappe.request.path or ""
		query = frappe.request.query_string.decode("utf-8") if frappe.request.query_string else ""
	except Exception:
		# No usable HTTP request context (server-side/internal call or tests).
		method = path = query = ""

	return "\n".join([method, path, query, timestamp, request_id or "", body])


def _validate_request_signature(settings):
	api_secret = settings.get("api_secret")

	if settings.get("auth_type") != "API Key" or not api_secret:
		# Signing is not fully configured. Internal/desk and server-side callers
		# are trusted, but an external token-authenticated request must never be
		# silently accepted without a signature — fail closed so a misconfigured
		# integration cannot downgrade the surface to token-only (SEC-08).
		if _is_external_api_request():
			frappe.throw(
				_("Request signing is not configured for this integration"),
				frappe.AuthenticationError,
			)
		return

	try:
		timestamp = frappe.get_request_header("X-Timestamp")
		signature = frappe.get_request_header("X-Signature")
		request_id = frappe.get_request_header("X-Request-ID")
	except RuntimeError:
		# No HTTP request context (server-side/internal call) — nothing to verify.
		return

	# A configured secret means signing is mandatory: reject unsigned requests so
	# the HMAC layer cannot be silently bypassed by omitting the headers.
	if not timestamp or not signature:
		frappe.throw(_("Request signature required"), frappe.AuthenticationError)

	# The nonce is part of the signed message and the replay/idempotency key, so
	# it must be present and cannot be tampered with independently of the body.
	if not request_id:
		frappe.throw(_("X-Request-ID header required"), frappe.AuthenticationError)

	try:
		ts = int(timestamp)
	except (TypeError, ValueError):
		frappe.throw(_("Invalid timestamp header"))

	if abs(int(time.time()) - ts) > SIGNATURE_TOLERANCE_SECONDS:
		frappe.throw(_("Request timestamp expired"))

	message = _build_signature_message(timestamp, request_id, _get_request_body())
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


def _idempotency_cache_key(fn_name, nonce):
	return f"{IDEMPOTENCY_CACHE_PREFIX}:{frappe.local.site}:{fn_name}:{nonce}"


def _idem_get(cache, key):
	try:
		raw = cache.get(key)
	except Exception:
		return None
	if raw is None:
		return None
	try:
		return json.loads(raw)
	except (ValueError, TypeError):
		return None


def _idem_store(cache, key, result):
	try:
		cache.set(key, json.dumps(result, default=str), ex=IDEMPOTENCY_TTL_SECONDS)
	except Exception:
		frappe.logger("custom_erpnext.api").warning(f"idempotency cache write skipped for {key}")


def _idem_acquire_lock(cache, lock_key):
	try:
		return bool(cache.set(lock_key, "1", nx=True, ex=IDEMPOTENCY_LOCK_SECONDS))
	except Exception:
		return False


def _idem_wait_for_result(cache, key):
	for _ in range(IDEMPOTENCY_WAIT_ATTEMPTS):
		time.sleep(IDEMPOTENCY_WAIT_INTERVAL)
		cached = _idem_get(cache, key)
		if cached is not None:
			return cached
	return None


def idempotent_write(fn):
	"""Make a write endpoint safe to retry and replay.

	Keyed on the transport nonce (``X-Request-ID``), which the client keeps
	stable across HTTP retries. A repeat call with the same nonce returns the
	stored response without re-executing the side effect, so neither a client
	retry nor a captured-request replay can create duplicate documents (e.g. a
	second Stock Reconciliation). Calls without a nonce (internal/desk) run
	normally. Apply *below* :func:`middleware_api` so authentication runs first
	and the nonce is available.
	"""

	@wraps(fn)
	def wrapper(*args, **kwargs):
		nonce = _get_request_nonce()
		if not nonce:
			return fn(*args, **kwargs)

		cache = frappe.cache
		key = _idempotency_cache_key(fn.__name__, nonce)

		cached = _idem_get(cache, key)
		if cached is not None:
			return cached

		lock_key = f"{key}:lock"
		locked = _idem_acquire_lock(cache, lock_key)
		if not locked:
			# A concurrent identical request holds the lock — wait for it to
			# publish its result instead of double-processing the side effect.
			waited = _idem_wait_for_result(cache, key)
			if waited is not None:
				return waited

		try:
			result = fn(*args, **kwargs)
			_idem_store(cache, key, result)
			return result
		finally:
			if locked:
				try:
					cache.delete(lock_key)
				except Exception:
					pass

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
