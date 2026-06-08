# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe


def success(data=None, meta=None, message=None):
	response = {"success": True, "data": data or {}, "errors": []}
	if meta:
		response["meta"] = meta
	if message:
		response["message"] = message
	return response


def error(message, code=None, errors=None, http_status=400):
	response = {
		"success": False,
		"data": {},
		"errors": errors or [{"message": message, "code": code or "VALIDATION_ERROR"}],
	}
	frappe.local.response["http_status_code"] = http_status
	return response


def paginated_meta(page, page_size, total):
	return {
		"page": page,
		"page_size": page_size,
		"total": total,
		"total_pages": (total + page_size - 1) // page_size if page_size else 0,
		"request_id": frappe.form_dict.get("request_id"),
	}
