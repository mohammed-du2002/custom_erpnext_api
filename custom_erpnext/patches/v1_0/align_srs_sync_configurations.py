# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe

from custom_erpnext.setup.laravel_integration import DEFAULT_SYNC_CONFIGS


def execute():
	"""Align sync configs with SRS §5.1 (10-min pull + urgent + full sync)."""
	frequency_updates = {
		"Pull Customers": "Every 10 Minutes",
		"Pull Promotions": "Every 10 Minutes",
		"Pull Discounts": "Every 10 Minutes",
	}

	for config_name, frequency in frequency_updates.items():
		if frappe.db.exists("Sync Configuration", config_name):
			frappe.db.set_value(
				"Sync Configuration",
				config_name,
				"frequency",
				frequency,
				update_modified=True,
			)

	if frappe.db.exists("Sync Configuration", "Pull Discounts"):
		frappe.db.set_value("Sync Configuration", "Pull Discounts", "entity", "Discount", update_modified=True)

	new_configs = [
		row
		for row in DEFAULT_SYNC_CONFIGS
		if row["config_name"]
		in (
			"Urgent Customer Changes",
			"Urgent Promotion Changes",
			"Urgent Discount Changes",
			"Full Sync Day Open",
		)
	]

	for row in new_configs:
		name = row["config_name"]
		values = {**row, "is_active": 1}
		if frappe.db.exists("Sync Configuration", name):
			doc = frappe.get_doc("Sync Configuration", name)
			doc.update(values)
			doc.save(ignore_permissions=True)
		else:
			doc = frappe.get_doc({"doctype": "Sync Configuration", **values})
			doc.insert(ignore_permissions=True)

	frappe.db.commit()
