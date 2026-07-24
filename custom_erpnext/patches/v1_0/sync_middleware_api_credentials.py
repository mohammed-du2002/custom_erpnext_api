# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe


def execute():
	"""Fix desynced middleware API secrets after deploy without bench console access."""
	from custom_erpnext.setup.laravel_integration import sync_integration_api_credentials

	sync_integration_api_credentials()
	frappe.db.commit()
