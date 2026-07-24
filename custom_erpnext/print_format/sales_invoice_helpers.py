"""
Sales Invoice KSA Modern — Jinja helper methods.
=================================================
Provides clean data-access methods for the print format template,
keeping business logic out of the HTML and avoiding duplicate DB queries.

Usage in Jinja (registered via hooks.py as jinja methods):
    {% set ctx = get_sales_invoice_print_context(doc) %}
"""
from __future__ import annotations

from typing import Optional

import frappe
from frappe.utils import cstr, flt


# ---------------------------------------------------------------------------
# Main context builder
# ---------------------------------------------------------------------------
def get_sales_invoice_print_context(doc) -> dict:
    """Build a unified context dict for the Sales Invoice KSA Modern print format.

    Returns a flat dict with all data needed by the template so that
    the Jinja layer doesn't need to make any DB calls itself.
    """
    company = _get_company_info(doc.company)
    company_address = _get_company_address(doc.company)
    customer = _get_customer_info(doc)
    qr_image_src = _get_qr_image_src(doc)

    return {
        "company": company,
        "company_address": company_address,
        "customer": customer,
        "qr_image_src": qr_image_src,
    }


# ---------------------------------------------------------------------------
# Company
# ---------------------------------------------------------------------------
def _get_company_info(company_name: str) -> dict:
    """Retrieve Company details relevant for the invoice header."""
    company_doc = frappe.get_cached_doc("Company", company_name)

    return {
        "name": cstr(company_doc.company_name),
        "name_arabic": cstr(company_doc.get("custom_company_name_arabic") or ""),
        "logo": cstr(company_doc.company_logo) if company_doc.company_logo else "",
        "tax_id": cstr(company_doc.tax_id or ""),
        "phone": cstr(company_doc.phone_no or ""),
        "email": cstr(company_doc.email or ""),
        "website": cstr(company_doc.website or company_doc.get("domain") or ""),
        "cr": cstr(
            company_doc.get("custom_commercial_registration")
            or company_doc.get("registration_details")
            or ""
        ),
    }


# ---------------------------------------------------------------------------
# Company Address
# ---------------------------------------------------------------------------
def _get_company_address(company_name: str) -> dict:
    """Retrieve the company's default / primary address."""
    empty = {
        "street": "",
        "street_arabic": "",
        "city": "",
        "city_arabic": "",
        "postal_code": "",
        "building_number": "",
        "district": "",
        "district_arabic": "",
        "country": "",
        "full_en": "",
        "full_ar": "",
    }

    # Try to find the primary address linked to the Company
    addresses = frappe.get_all(
        "Dynamic Link",
        filters={
            "parenttype": "Address",
            "link_doctype": "Company",
            "link_name": company_name,
        },
        pluck="parent",
        limit=5,
    )

    if not addresses:
        return empty

    # Prefer the address flagged as "is_your_company_address"
    address_doc = None
    for addr_name in addresses:
        addr = frappe.get_cached_doc("Address", addr_name)
        if addr.is_your_company_address:
            address_doc = addr
            break
    if not address_doc:
        address_doc = frappe.get_cached_doc("Address", addresses[0])

    street = cstr(address_doc.address_line1 or "")
    city = cstr(address_doc.city or "")
    district = cstr(address_doc.get("custom_area") or address_doc.get("county") or "")
    postal_code = cstr(address_doc.pincode or "")
    building_number = cstr(address_doc.get("custom_building_number") or "")
    country = cstr(address_doc.country or "")

    # Build human-readable full address strings
    parts_en = [p for p in [building_number, street, district, city, postal_code, country] if p]
    full_en = ", ".join(parts_en)

    # Arabic versions — use same data (system may not store Arabic addresses separately)
    street_arabic = cstr(address_doc.get("address_line2") or "")
    city_arabic = ""  # Can be extended if custom field exists
    district_arabic = ""  # Can be extended if custom field exists

    parts_ar = [p for p in [building_number, street_arabic or street, district, city, postal_code] if p]
    full_ar = "، ".join(parts_ar)

    return {
        "street": street,
        "street_arabic": street_arabic,
        "city": city,
        "city_arabic": city_arabic,
        "postal_code": postal_code,
        "building_number": building_number,
        "district": district,
        "district_arabic": district_arabic,
        "country": country,
        "full_en": full_en,
        "full_ar": full_ar,
    }


# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------
def _get_customer_info(doc) -> dict:
    """Retrieve customer details for the invoice."""
    customer_doc = frappe.get_cached_doc("Customer", doc.customer)

    # Customer address
    address = _get_customer_address_info(doc, customer_doc)

    return {
        "name": cstr(doc.customer_name or doc.customer),
        "name_arabic": cstr(customer_doc.get("custom_customer_name_arabic") or ""),
        "tax_id": cstr(
            customer_doc.get("custom_vat_registration_number")
            or customer_doc.get("tax_id")
            or ""
        ),
        "phone": cstr(doc.get("contact_phone") or doc.get("contact_mobile") or ""),
        "email": cstr(doc.get("contact_email") or ""),
        "customer_code": cstr(customer_doc.get("customer_code") or customer_doc.name),
        "cr": cstr(customer_doc.get("id_number") or ""),
        "address": address,
    }


def _get_customer_address_info(doc, customer_doc) -> dict:
    """Extract customer address from the invoice or the customer's primary address."""
    empty = {"full": "", "street": "", "city": "", "postal_code": "", "district": "", "country": ""}

    # First try to get from the invoice's customer_address field
    if doc.customer_address:
        try:
            addr = frappe.get_cached_doc("Address", doc.customer_address)
            street = cstr(addr.address_line1 or "")
            city = cstr(addr.city or "")
            district = cstr(addr.get("custom_area") or "")
            postal_code = cstr(addr.pincode or "")
            country = cstr(addr.country or "")
            building = cstr(addr.get("custom_building_number") or "")
            parts = [p for p in [building, street, district, city, postal_code, country] if p]
            return {
                "full": ", ".join(parts),
                "street": street,
                "city": city,
                "postal_code": postal_code,
                "district": district,
                "country": country,
            }
        except Exception:
            pass

    # Fallback: use address_display from invoice
    if doc.address_display:
        return {"full": cstr(doc.address_display).replace("<br>", ", ").replace("\n", ", "),
                "street": "", "city": "", "postal_code": "", "district": "", "country": ""}

    return empty


# ---------------------------------------------------------------------------
# QR Code (ksa_compliance integration)
# ---------------------------------------------------------------------------
def _get_qr_image_src(doc) -> str:
    """Retrieve the ZATCA QR code image from ksa_compliance.

    Strategy (in order of preference):
    1. Phase 2: Use get_phase_2_print_format_details → siaf.qr_image_src
    2. Phase 1: Use get_zatca_phase_1_qr_for_invoice → base64 PNG
    3. Return empty string if no QR available
    """
    # Phase 2: Check for Sales Invoice Additional Fields
    try:
        from ksa_compliance.jinja import get_phase_2_print_format_details

        details = get_phase_2_print_format_details(doc)
        if details and details.get("siaf") and details["siaf"].qr_image_src:
            return details["siaf"].qr_image_src
    except (ImportError, Exception):
        pass

    # Phase 1: Generate QR from invoice data
    try:
        from ksa_compliance.jinja import get_zatca_phase_1_qr_for_invoice

        qr_base64 = get_zatca_phase_1_qr_for_invoice(doc.name)
        if qr_base64:
            return f"data:image/png;base64,{qr_base64}"
    except (ImportError, Exception):
        pass

    return ""


# ---------------------------------------------------------------------------
# Utility: Tax details for items
# ---------------------------------------------------------------------------
def get_item_tax_details(doc) -> dict:
    """Get per-item tax rate and amount using ksa_compliance helpers.

    Returns a dict keyed by item row name: {row_name: {rate, amount}}
    Falls back to zero if ksa_compliance is unavailable.
    """
    try:
        from ksa_compliance.jinja import get_item_wise_tax_details

        return get_item_wise_tax_details(doc)
    except (ImportError, Exception):
        # Fallback: return empty tax info
        return {item.name: {"rate": flt(item.get("tax_rate", 0)),
                            "amount": flt(item.get("tax_amount", 0))}
                for item in doc.items}


# ---------------------------------------------------------------------------
# Utility: VAT percentage from taxes table
# ---------------------------------------------------------------------------
def get_vat_percentage(doc) -> float:
    """Extract the VAT percentage from the taxes table.

    Returns the first tax rate found (typically 15% for KSA),
    or 0 if no taxes are configured.
    """
    if doc.taxes:
        for tax in doc.taxes:
            if flt(tax.rate) > 0:
                return flt(tax.rate)
    return 0.0


# ---------------------------------------------------------------------------
# Utility: Sales person name
# ---------------------------------------------------------------------------
def get_sales_person(doc) -> str:
    """Get the primary sales person name from the invoice."""
    # Check custom field first
    if doc.get("sales_representative"):
        return cstr(doc.sales_representative)

    # Check sales_team child table
    if doc.get("sales_team") and len(doc.sales_team) > 0:
        return cstr(doc.sales_team[0].sales_person)

    return ""
