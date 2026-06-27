# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe


def execute():
	"""Add Push Cashier Movements sync configuration on existing sites."""
	config = {
		"config_name": "Push Cashier Movements",
		"sync_type": "Push (POS→ERP)",
		"entity": "Cashier Movement",
		"frequency": "Manual",
		"batch_size": 50,
		"timeout_seconds": 60,
		"retry_attempts": 5,
		"is_active": 1,
	}

	name = config["config_name"]
	if frappe.db.exists("Sync Configuration", name):
		doc = frappe.get_doc("Sync Configuration", name)
		doc.update(config)
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc({"doctype": "Sync Configuration", **config})
		doc.insert(ignore_permissions=True)

	frappe.db.commit()
