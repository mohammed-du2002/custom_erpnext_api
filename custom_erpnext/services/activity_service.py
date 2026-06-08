# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe


def log_activity(
	activity_type,
	user=None,
	document_type=None,
	document_name=None,
	description=None,
	branch=None,
	pos_device=None,
):
	"""Create a User Activity Monitor entry."""
	try:
		doc = frappe.get_doc(
			{
				"doctype": "User Activity Monitor",
				"user": user or frappe.session.user,
				"activity_type": activity_type,
				"document_type": document_type,
				"document_name": document_name,
				"description": description,
				"branch": branch,
				"pos_device": pos_device,
				"ip_address": frappe.local.request_ip if getattr(frappe.local, "request_ip", None) else None,
			}
		)
		doc.insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="User Activity Monitor Log Failed")
