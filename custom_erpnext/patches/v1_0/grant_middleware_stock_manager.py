# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe


def execute():
	"""Stock Reconciliation apply via middleware requires Stock Manager + branch access."""
	from custom_erpnext.setup.laravel_integration import (
		_sync_user_branch_access,
		fix_middleware_user_roles,
		INTEGRATION_USER,
	)

	fix_middleware_user_roles()
	_sync_user_branch_access(INTEGRATION_USER)
	frappe.db.commit()
