# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Optional GL posting for cashier movements (controlled per company)."""

import frappe
from frappe import _
from frappe.utils import flt, getdate


MOVEMENT_GL_HANDLERS = {
	"Shift Close": "_post_shift_variance_gl",
	"Petty Cash": "_post_petty_cash_gl",
	"Bank Deposit": "_post_bank_deposit_gl",
}


def maybe_post_movement_gl(shift_doc, movement_doc, data):
	"""Post accounting entries when enabled on the company."""
	if not _is_gl_enabled(shift_doc.company):
		return None

	handler_name = MOVEMENT_GL_HANDLERS.get(movement_doc.movement_type)
	if not handler_name:
		return None

	handler = globals()[handler_name]
	return handler(shift_doc, movement_doc, data)


def _is_gl_enabled(company):
	return bool(frappe.db.get_value("Company", company, "post_cashier_movement_gl"))


def _get_cash_account(company, pos_device=None):
	account = frappe.db.get_value("Company", company, "pos_cash_account")
	if account:
		return account

	if pos_device:
		pos_profile = frappe.db.get_value("POS Device", pos_device, "pos_profile")
		if pos_profile:
			cash_row = frappe.db.get_value(
				"POS Payment Method",
				{"parent": pos_profile, "mode_of_payment": "Cash"},
				"default_account",
			)
			if cash_row:
				return cash_row

	mode_account = frappe.db.get_value(
		"Mode of Payment Account",
		{"parent": "Cash", "company": company},
		"default_account",
	)
	return mode_account


def _create_journal_entry(company, posting_date, accounts, remark, reference_doc=None):
	je = frappe.new_doc("Journal Entry")
	je.voucher_type = "Journal Entry"
	je.company = company
	je.posting_date = getdate(posting_date)
	je.user_remark = remark

	for row in accounts:
		je.append(
			"accounts",
			{
				"account": row["account"],
				"debit_in_account_currency": flt(row.get("debit")),
				"credit_in_account_currency": flt(row.get("credit")),
				"cost_center": row.get("cost_center"),
			},
		)

	if reference_doc:
		je.cheque_no = reference_doc.get("name")
		je.cheque_date = getdate(posting_date)

	je.flags.ignore_permissions = True
	je.insert()
	je.submit()
	return je.name


def _post_shift_variance_gl(shift_doc, movement_doc, data):
	variance = flt(shift_doc.variance)
	if abs(variance) < 0.01:
		return None

	company = shift_doc.company
	cash_account = _get_cash_account(company, shift_doc.pos_device)
	if not cash_account:
		frappe.throw(_("Cash account is not configured for company {0}").format(company))

	cost_center = frappe.db.get_value("Company Branch", shift_doc.branch, "cost_center")
	short_account = frappe.db.get_value("Company", company, "cash_short_account")
	over_account = frappe.db.get_value("Company", company, "cash_over_account")

	accounts = []
	if variance < 0:
		if not short_account:
			frappe.throw(_("Cash Short Account is required on Company {0}").format(company))
		accounts = [
			{"account": short_account, "debit": abs(variance), "cost_center": cost_center},
			{"account": cash_account, "credit": abs(variance), "cost_center": cost_center},
		]
	else:
		if not over_account:
			frappe.throw(_("Cash Over Account is required on Company {0}").format(company))
		accounts = [
			{"account": cash_account, "debit": variance, "cost_center": cost_center},
			{"account": over_account, "credit": variance, "cost_center": cost_center},
		]

	je_name = _create_journal_entry(
		company,
		movement_doc.movement_datetime,
		accounts,
		_("POS shift cash variance {0}").format(shift_doc.name),
		reference_doc=shift_doc,
	)
	shift_doc.db_set({"journal_entry": je_name, "gl_posted": 1}, update_modified=True)
	return je_name


def _post_petty_cash_gl(shift_doc, movement_doc, data):
	amount = abs(flt(movement_doc.amount))
	if amount <= 0:
		return None

	company = shift_doc.company
	cash_account = _get_cash_account(company, shift_doc.pos_device)
	expense_account = frappe.db.get_value("Company", company, "petty_cash_expense_account")
	if not cash_account or not expense_account:
		return None

	cost_center = frappe.db.get_value("Company Branch", shift_doc.branch, "cost_center")
	je_name = _create_journal_entry(
		company,
		movement_doc.movement_datetime,
		[
			{"account": expense_account, "debit": amount, "cost_center": cost_center},
			{"account": cash_account, "credit": amount, "cost_center": cost_center},
		],
		movement_doc.reason or _("Petty cash"),
		reference_doc=movement_doc,
	)
	movement_doc.db_set("journal_entry", je_name, update_modified=True)
	return je_name


def _post_bank_deposit_gl(shift_doc, movement_doc, data):
	amount = abs(flt(movement_doc.amount))
	if amount <= 0:
		return None

	company = shift_doc.company
	cash_account = _get_cash_account(company, shift_doc.pos_device)
	bank_account = data.get("bank_account") or frappe.db.get_value("Company", company, "default_bank_account")
	if not cash_account or not bank_account:
		return None

	cost_center = frappe.db.get_value("Company Branch", shift_doc.branch, "cost_center")
	je_name = _create_journal_entry(
		company,
		movement_doc.movement_datetime,
		[
			{"account": bank_account, "debit": amount, "cost_center": cost_center},
			{"account": cash_account, "credit": amount, "cost_center": cost_center},
		],
		movement_doc.remarks or _("Bank deposit"),
		reference_doc=movement_doc,
	)
	movement_doc.db_set("journal_entry", je_name, update_modified=True)
	return je_name
