# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Retail stock settings required by the offline-first POS (SRS §8.4)."""

import frappe
from frappe.utils import cint


def enable_negative_stock_for_retail():
	"""Allow negative selling so offline POS sales never block on sync.

	The offline-first POS (SRS §8.4 "السماح بالبيع بالسالب") can sell stock that
	ERPNext has not yet received. Because POS Sales Invoices are forced to
	``update_stock = 1``, submitting them would otherwise fail the moment a bin
	goes negative, leaving invoices stuck in a failed sync state. Enable the
	global Stock Settings flag idempotently and upgrade-safely.
	"""
	if cint(frappe.db.get_single_value("Stock Settings", "allow_negative_stock")):
		return False

	frappe.db.set_single_value("Stock Settings", "allow_negative_stock", 1)
	frappe.logger("custom_erpnext").info(
		"Enabled Stock Settings.allow_negative_stock for retail POS (SRS 8.4)"
	)
	return True
