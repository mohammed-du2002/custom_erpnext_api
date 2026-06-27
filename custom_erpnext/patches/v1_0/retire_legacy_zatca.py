# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Retire the legacy custom ZATCA engine now that ksa_compliance owns ZATCA.

Removes the ``ZATCA Invoice`` and ``ZATCA Configuration`` DocTypes (and their
tables / leftover metadata). Retail display fields on Sales Invoice
(``zatca_status``, ``zatca_reference``, ``zatca_sync_status``, ``e_invoice_type``,
``is_e_invoice``, ``pi_number``) are kept as a read-only mirror fed from
ksa_compliance's Sales Invoice Additional Fields.
"""

import frappe

LEGACY_DOCTYPES = ("ZATCA Invoice", "ZATCA Configuration")


def execute():
	for doctype in LEGACY_DOCTYPES:
		if frappe.db.exists("DocType", doctype):
			frappe.delete_doc("DocType", doctype, force=True, ignore_permissions=True, ignore_missing=True)

		# Drop the backing table if it is still around.
		table = f"tab{doctype}"
		if frappe.db.table_exists(doctype):
			frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `{table}`")

		# Clean any leftover metadata that references the retired doctypes.
		frappe.db.delete("Custom Field", {"dt": doctype})
		frappe.db.delete("Property Setter", {"doc_type": doctype})
		frappe.db.delete("Custom DocPerm", {"parent": doctype})

	frappe.clear_cache()
