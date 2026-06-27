# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe


REMOVED_SALES_INVOICE_FIELDS = (
	"retail_approval_section",
	"approved_by",
	"approval_date",
	"discount_authorized_by",
)


def cleanup_removed_sales_invoice_fields():
	"""Remove approval custom fields that were dropped from fixtures."""
	for fieldname in REMOVED_SALES_INVOICE_FIELDS:
		custom_field = frappe.db.get_value(
			"Custom Field", {"dt": "Sales Invoice", "fieldname": fieldname}
		)
		if custom_field:
			frappe.delete_doc("Custom Field", custom_field, force=True, ignore_permissions=True)

	frappe.clear_cache(doctype="Sales Invoice")
