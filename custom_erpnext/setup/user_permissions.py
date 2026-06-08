# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe

from custom_erpnext.services.branch_permission_service import (
	sync_profile_branch_permissions,
	sync_user_branch_permissions,
)


def sync_all_user_branch_permissions():
	"""Rebuild Frappe User Permissions from profile and user defaults."""
	synced_users = set()

	for profile_name in frappe.get_all("User Discount Profile", pluck="name"):
		doc = frappe.get_doc("User Discount Profile", profile_name)
		sync_profile_branch_permissions(doc)
		synced_users.add(doc.user)

	for user_row in frappe.get_all(
		"User",
		filters={"branch": ["is", "set"], "enabled": 1},
		fields=["name", "branch"],
	):
		if user_row.name in synced_users:
			continue
		sync_user_branch_permissions(user_row.name, fallback_branch=user_row.branch)

	frappe.db.commit()
