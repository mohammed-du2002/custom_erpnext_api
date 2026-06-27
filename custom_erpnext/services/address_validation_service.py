# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""ZATCA-compliant Saudi customer address validation (buyer address)."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import get_link_to_form


def get_address_doc(address_name: str | None):
	if not address_name:
		return None
	if not frappe.db.exists("Address", address_name):
		return None
	return frappe.get_doc("Address", address_name)


def collect_zatca_address_issues(address) -> list[str]:
	"""Return human-readable validation messages for a buyer Address."""
	if not address:
		return [_("Customer address is required for B2B e-invoicing.")]

	issues: list[str] = []
	if not (address.address_line1 or "").strip():
		issues.append(_("Please set Address Line 1 for customer address."))

	building_number = (address.get("custom_building_number") or "").strip()
	if not building_number:
		issues.append(_("Please set a building number for customer address."))
	elif address.country == "Saudi Arabia" and len(building_number) != 4:
		issues.append(
			_("Please make sure that building number is 4 digits exactly in customer address.")
		)

	if not (address.city or "").strip():
		issues.append(_("Please set city for customer address."))

	pincode = (address.pincode or "").strip()
	if address.country == "Saudi Arabia" and (not pincode or len(pincode) != 5):
		issues.append(
			_("Please make sure that postal code is set and is 5 digits exactly in customer address.")
		)

	if not (address.get("custom_area") or "").strip():
		issues.append(_("Please set district for customer address."))

	return issues


def validate_zatca_customer_address(address_name: str | None) -> dict:
	"""Non-throwing validation used by desk UI and APIs."""
	address = get_address_doc(address_name)
	issues = collect_zatca_address_issues(address)
	return {
		"valid": not issues,
		"issues": issues,
		"address": address_name if address else None,
		"edit_url": get_link_to_form("Address", address_name) if address_name else None,
	}


def throw_if_invalid_zatca_address(address_name: str | None):
	"""Raise with actionable link when address fails ZATCA buyer rules."""
	result = validate_zatca_customer_address(address_name)
	if result["valid"]:
		return

	message_parts = list(result["issues"])
	if result.get("edit_url"):
		message_parts.append(result["edit_url"])
	frappe.throw("<hr>".join(message_parts), title=_("Invalid Address Error"))
