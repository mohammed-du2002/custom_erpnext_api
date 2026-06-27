# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Backfill is_pos_transaction for existing POS-synced Sales Invoices."""


import frappe


def execute():
	if not frappe.db.has_column("Sales Invoice", "is_pos_transaction"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabSales Invoice`
		SET is_pos_transaction = 1
		WHERE IFNULL(is_pos_transaction, 0) = 0
			AND (
				IFNULL(offline_invoice_id, '') != ''
				OR IFNULL(pos_device, '') != ''
				OR IFNULL(is_pos, 0) = 1
			)
		"""
	)
