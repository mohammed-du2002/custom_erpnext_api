# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Replace legacy ZATCA technical fields on Sales Invoice with retail tracking fields."""

import frappe


REMOVED_FIELDS = (
	"zatca_uuid",
	"xml_content",
	"signed_xml",
	"private_key",
	"certificate",
	"csid",
	"pih",
	"previous_invoice_hash",
)


def execute():
	if (
		frappe.db.has_column("Sales Invoice", "zatca_uuid")
		and frappe.db.has_column("Sales Invoice", "zatca_reference")
	):
		frappe.db.sql(
			"""
			UPDATE `tabSales Invoice`
			SET zatca_reference = COALESCE(NULLIF(zatca_reference, ''), zatca_uuid)
			WHERE IFNULL(zatca_uuid, '') != ''
			"""
		)

	for fieldname in REMOVED_FIELDS:
		custom_field = frappe.db.get_value(
			"Custom Field", {"dt": "Sales Invoice", "fieldname": fieldname}
		)
		if custom_field:
			frappe.delete_doc("Custom Field", custom_field, force=True, ignore_permissions=True)

	frappe.clear_cache(doctype="Sales Invoice")
