# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Delete orphaned Custom Field rows whose fieldname collides with a standard
field on the same DocType.

These rows cause `UniqueFieldnameError: Fieldname X appears multiple times`
during `bench migrate` / app install on sites that were migrated with an older
version of the fixtures (e.g. a custom ``Item-max_discount`` field that clashes
with the standard ERPNext ``Item.max_discount``).

Runs in ``pre_model_sync`` so the bad rows are gone before the DocType meta is
rebuilt and validated.
"""

import frappe

# (DocType, fieldname) pairs that exist as STANDARD fields and must never be
# redefined as Custom Fields.
CONFLICTING_FIELDS = (
	("Item", "max_discount"),
	("Item", "customer_code"),
	("Item", "allow_negative_stock"),
)


def execute():
	deleted = []
	for doctype, fieldname in CONFLICTING_FIELDS:
		for name in frappe.get_all(
			"Custom Field",
			filters={"dt": doctype, "fieldname": fieldname},
			pluck="name",
		):
			frappe.db.delete("Custom Field", {"name": name})
			deleted.append(name)

	if deleted:
		frappe.clear_cache()
		frappe.logger("custom_erpnext").info(
			"Removed conflicting custom fields: %s", ", ".join(deleted)
		)
