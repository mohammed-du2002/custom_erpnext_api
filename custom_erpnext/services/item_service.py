# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe import _


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
