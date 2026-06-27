# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{
			"label": _("Shift"),
			"fieldname": "shift",
			"fieldtype": "Link",
			"options": "POS Cashier Shift",
			"width": 140,
		},
		{
			"label": _("Shift ID"),
			"fieldname": "shift_id",
			"fieldtype": "Data",
			"width": 140,
		},
		{
			"label": _("Branch"),
			"fieldname": "branch",
			"fieldtype": "Link",
			"options": "Company Branch",
			"width": 100,
		},
		{
			"label": _("POS Device"),
			"fieldname": "pos_device",
			"fieldtype": "Link",
			"options": "POS Device",
			"width": 120,
		},
		{
			"label": _("Cashier"),
			"fieldname": "cashier",
			"fieldtype": "Link",
			"options": "User",
			"width": 140,
		},
		{
			"label": _("Summary Date"),
			"fieldname": "summary_date",
			"fieldtype": "Date",
			"width": 100,
		},
		{
			"label": _("Shift Closing Cash"),
			"fieldname": "shift_closing_cash",
			"fieldtype": "Currency",
			"width": 120,
		},
		{
			"label": _("DSS Closing Cash"),
			"fieldname": "dss_closing_cash",
			"fieldtype": "Currency",
			"width": 120,
		},
		{
			"label": _("Shift Variance"),
			"fieldname": "shift_variance",
			"fieldtype": "Currency",
			"width": 110,
		},
		{
			"label": _("DSS Variance"),
			"fieldname": "dss_variance",
			"fieldtype": "Currency",
			"width": 110,
		},
		{
			"label": _("Reconciliation Delta"),
			"fieldname": "reconciliation_delta",
			"fieldtype": "Currency",
			"width": 130,
		},
	]


def get_data(filters):
	filters = frappe._dict(filters or {})
	conditions = ["pcs.status = 'Closed'"]
	values = {}

	if filters.get("branch"):
		conditions.append("pcs.branch = %(branch)s")
		values["branch"] = filters.branch

	if filters.get("from_date"):
		conditions.append("DATE(pcs.closing_datetime) >= %(from_date)s")
		values["from_date"] = getdate(filters.from_date)

	if filters.get("to_date"):
		conditions.append("DATE(pcs.closing_datetime) <= %(to_date)s")
		values["to_date"] = getdate(filters.to_date)

	where_clause = " AND ".join(conditions)
	rows = frappe.db.sql(
		f"""
		SELECT
			pcs.name AS shift,
			pcs.shift_id,
			pcs.branch,
			pcs.pos_device,
			pcs.cashier,
			dss.summary_date,
			pcs.closing_cash AS shift_closing_cash,
			dss.closing_cash AS dss_closing_cash,
			pcs.variance AS shift_variance,
			dss.variance AS dss_variance
		FROM `tabPOS Cashier Shift` pcs
		LEFT JOIN `tabDaily Sales Summary` dss ON dss.name = pcs.daily_sales_summary
		WHERE {where_clause}
		ORDER BY pcs.closing_datetime DESC
		""",
		values,
		as_dict=True,
	)

	for row in rows:
		shift_close = flt(row.shift_closing_cash)
		dss_close = flt(row.dss_closing_cash)
		row.reconciliation_delta = shift_close - dss_close

	return rows
