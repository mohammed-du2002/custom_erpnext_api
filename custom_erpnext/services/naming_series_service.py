# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.naming import NamingSeries
from frappe.utils import cint

# Series options end with "." so Frappe appends ".#####" → e.g. SINV-BR1-.00001
BRANCH_NAMING_TEMPLATES = {
	"Sales Invoice": {
		"default": "SINV-{branch}-.",
		"return": "SINV-RET-{branch}-.",
	},
	"Material Request": "MR-{branch}-.",
	"Purchase Order": "PO-{branch}-.",
	"Purchase Invoice": "PI-{branch}-.",
	"Purchase Receipt": "PR-{branch}-.",
	"Daily Sales Summary": "DSS-{branch}-.",
	"Stock Transfer Request": "STR-{branch}-.",
	"POS Cashier Shift": "PCS-{branch}-.",
	"Cashier Movement": "CMV-{branch}-.",
}

BRANCH_NAMING_DOCTYPES = list(BRANCH_NAMING_TEMPLATES.keys())


def get_branch_code(branch):
	if not branch:
		return None
	return frappe.db.get_value("Company Branch", branch, "branch_code")


def resolve_branch_series(doctype, branch_code, is_return=False):
	if not branch_code:
		return None

	template = BRANCH_NAMING_TEMPLATES.get(doctype)
	if not template:
		return None

	if isinstance(template, dict):
		key = "return" if cint(is_return) else "default"
		template = template.get(key)
		if not template:
			return None

	series = template.format(branch=branch_code)
	NamingSeries(series).validate()
	return series


def get_naming_series_for_branch(doctype, branch, is_return=False):
	branch_code = get_branch_code(branch)
	return resolve_branch_series(doctype, branch_code, is_return=is_return)


def get_naming_series_for_doc(doc):
	is_return = doc.doctype == "Sales Invoice" and cint(doc.get("is_return"))
	return get_naming_series_for_branch(doc.doctype, doc.get("branch"), is_return=is_return)


def apply_branch_naming_series(doc, method=None):
	if not doc.is_new() or not doc.meta.get_field("naming_series"):
		return

	series = get_naming_series_for_doc(doc)
	if series:
		doc.naming_series = series


def register_branch_naming_series(branch_doc):
	branch_code = (branch_doc.branch_code or "").strip().upper()
	if not branch_code:
		return

	for doctype in BRANCH_NAMING_DOCTYPES:
		template = BRANCH_NAMING_TEMPLATES[doctype]
		if isinstance(template, dict):
			series_list = [
				resolve_branch_series(doctype, branch_code, is_return=False),
				resolve_branch_series(doctype, branch_code, is_return=True),
			]
		else:
			series_list = [resolve_branch_series(doctype, branch_code)]

		for series in series_list:
			if series:
				_append_naming_series_option(doctype, series)


def _append_naming_series_option(doctype, series):
	if not frappe.get_meta(doctype).get_field("naming_series"):
		return

	current_options = frappe.get_meta(doctype).get_naming_series_options()
	if series in current_options:
		return

	options = list(current_options)
	options.append(series)

	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	make_property_setter(
		doctype,
		"naming_series",
		"options",
		"\n".join(options),
		"Text",
		validate_fields_for_doctype=False,
	)
	frappe.clear_cache(doctype=doctype)
