# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt, getdate


def pull_cashier_shifts(
	branch=None,
	pos_device=None,
	status=None,
	modified_from=None,
	include_movements=0,
	page=1,
	page_size=50,
):
	"""Pull POS cashier shifts for manager dashboards / reconciliation."""
	from custom_erpnext.services.pull_service import get_modified_filter

	filters = get_modified_filter(modified_from)
	if branch is not None:
		from custom_erpnext.services.pull_service import _branch_clause

		filters["branch"] = _branch_clause(branch)
	if pos_device:
		filters["pos_device"] = pos_device
	if status:
		filters["status"] = status

	total = frappe.db.count("POS Cashier Shift", filters)
	offset = (page - 1) * page_size
	shifts = frappe.get_all(
		"POS Cashier Shift",
		filters=filters,
		fields=[
			"name",
			"offline_shift_id",
			"shift_id",
			"company",
			"branch",
			"pos_device",
			"cashier",
			"status",
			"opening_datetime",
			"closing_datetime",
			"opening_cash",
			"expected_cash",
			"closing_cash",
			"variance",
			"daily_sales_summary",
			"journal_entry",
			"gl_posted",
			"sync_status",
			"sync_time",
			"modified",
		],
		order_by="modified desc",
		limit_page_length=page_size,
		limit_start=offset,
	)

	if frappe.utils.cint(include_movements):
		for shift in shifts:
			shift["movements"] = _get_shift_movements(shift.name)

	return shifts, total


def _get_shift_movements(shift_name):
	return frappe.get_all(
		"Cashier Movement",
		filters={"pos_cashier_shift": shift_name},
		fields=[
			"name",
			"offline_movement_id",
			"movement_type",
			"movement_datetime",
			"amount",
			"direction",
			"opening_balance",
			"closing_balance",
			"reason",
			"approved_by",
			"remarks",
			"journal_entry",
			"sync_status",
		],
		order_by="movement_datetime asc",
	)


def link_shift_to_daily_sales_summary(shift_doc, movement_datetime):
	"""Link closed shift to Daily Sales Summary for the same device/day."""
	if shift_doc.daily_sales_summary:
		return shift_doc.daily_sales_summary

	summary_date = getdate(movement_datetime)
	summary_name = frappe.db.get_value(
		"Daily Sales Summary",
		{
			"summary_date": summary_date,
			"branch": shift_doc.branch,
			"pos_device": shift_doc.pos_device,
		},
		"name",
	)
	if summary_name:
		shift_doc.daily_sales_summary = summary_name
	return summary_name
