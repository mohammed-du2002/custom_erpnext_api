# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import cint, flt


def validate_composite_item(doc, method=None):
	"""Composite items (SRS §3.3.3) must reference a Product Bundle of components."""
	if not cint(doc.get("is_composite")):
		return

	if not doc.get("composite_bundle"):
		frappe.throw(_("Composite items require a Product Bundle (Composite Bundle)"))

	if not frappe.db.exists("Product Bundle", doc.composite_bundle):
		frappe.throw(_("Product Bundle {0} does not exist").format(doc.composite_bundle))


def get_composite_components(item_code):
	"""Return the Product Bundle components for a composite item, or []."""
	item = frappe.db.get_value("Item", item_code, ["is_composite", "composite_bundle"], as_dict=True)
	if not item or not cint(item.is_composite) or not item.composite_bundle:
		return []

	return frappe.get_all(
		"Product Bundle Item",
		filters={"parent": item.composite_bundle},
		fields=["item_code", "qty", "uom"],
		order_by="idx asc",
	)


def explode_composite_items(doc, method=None):
	"""Deduct components when a composite item is sold (SRS §3.3.3).

	ERPNext only auto-explodes a line into ``packed_items`` when a Product Bundle
	exists whose ``new_item_code`` matches the sold item. Composite retail items
	point at a bundle through ``composite_bundle`` (which may be named
	differently), so we populate the packing list for those lines ourselves. Lines
	already handled natively by ERPNext are skipped to avoid double deduction.
	"""
	if not doc.get("items"):
		return

	for line in doc.get("items"):
		if not line.get("item_code"):
			continue

		# ERPNext already explodes bundles keyed by item_code.
		if frappe.db.exists("Product Bundle", {"new_item_code": line.item_code}):
			continue

		components = get_composite_components(line.item_code)
		if not components:
			continue

		for comp in components:
			doc.append(
				"packed_items",
				{
					"parent_item": line.item_code,
					"item_code": comp["item_code"],
					"qty": flt(line.qty) * flt(comp["qty"]),
					"uom": comp.get("uom"),
					"warehouse": line.get("warehouse") or doc.get("set_warehouse"),
					"parent_detail_docname": line.get("name"),
				},
			)


def validate_selling_prices(doc, method=None):
	if not doc.min_selling_price and not doc.max_selling_price:
		return

	standard_rate = doc.standard_rate or 0
	if doc.min_selling_price and standard_rate and standard_rate < doc.min_selling_price:
		frappe.throw(
			_("Standard Rate {0} cannot be less than Min Selling Price {1}").format(
				standard_rate, doc.min_selling_price
			)
		)

	if doc.max_selling_price and standard_rate and standard_rate > doc.max_selling_price:
		frappe.throw(
			_("Standard Rate {0} cannot exceed Max Selling Price {1}").format(
				standard_rate, doc.max_selling_price
			)
		)

	if (
		doc.min_selling_price
		and doc.max_selling_price
		and doc.min_selling_price > doc.max_selling_price
	):
		frappe.throw(_("Min Selling Price cannot be greater than Max Selling Price"))
