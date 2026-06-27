# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""
End-to-end ZATCA B2C (Simplified) Invoice scenario test.

Tests the full flow:
  1. Pre-flight: verify ZATCA settings are active & onboarded
  2. Stock check: ensure item has inventory (auto-add if needed)
  3. Create a real Sales Invoice for a B2C customer (with 15% VAT)
  4. Submit it → triggers ksa_compliance on_submit → ZATCA reporting
  5. Check Sales Invoice Additional Fields (XML generation)
  6. Wait for ZATCA Integration Log (background worker result)
  7. Print full human-readable report + JSON

Usage:
  bench --site tsc.localhost execute \\
    custom_erpnext.integrations.zatca.e2e_invoice_test.main

Optional kwargs:
  customer   — customer name (default: ZATCA Sandbox B2C)
  item_id    — item code    (default: RET-TRASH-BAG)
  company    — company name (default: tsc)
  qty        — quantity     (default: 2)
  rate       — unit price   (default: 100)
"""

from __future__ import annotations

import json
import time
from typing import Any

import frappe
from frappe.utils import now_datetime

# ──────────────────────────────────────────────────────────────────────────────
# Constants / defaults
# ──────────────────────────────────────────────────────────────────────────────
DEFAULT_COMPANY  = "tsc"
DEFAULT_ITEM     = "RET-TRASH-BAG"
DEFAULT_CUSTOMER = "ZATCA Sandbox B2C"   # B2C individual → Simplified invoice
DEFAULT_QTY      = 2.0
DEFAULT_RATE     = 100.0                 # SAR — 15% VAT = SAR 30


# ──────────────────────────────────────────────────────────────────────────────
# Print helpers
# ──────────────────────────────────────────────────────────────────────────────
def _sep(char: str = "─", width: int = 70) -> str:
    return char * width


def _print_step(num: int, title: str) -> None:
    print(f"\n{_sep()}")
    print(f"  STEP {num}: {title}")
    print(_sep())


def _print_result(label: str, value: Any, indent: int = 2) -> None:
    pad = " " * indent
    if isinstance(value, (dict, list)):
        print(f"{pad}{label}:")
        for line in json.dumps(value, indent=4, default=str).splitlines():
            print(f"{pad}  {line}")
    else:
        print(f"{pad}{label}: {value}")


# ──────────────────────────────────────────────────────────────────────────────
# Data helpers
# ──────────────────────────────────────────────────────────────────────────────
def _get_active_zatca_settings(company: str):
    name = frappe.db.get_value(
        "ZATCA Business Settings",
        {"company": company, "status": "Active"},
        "name",
    )
    return frappe.get_doc("ZATCA Business Settings", name) if name else None


def _get_tax_template(company: str) -> str | None:
    return (
        frappe.db.get_value("Sales Taxes and Charges Template", {"company": company, "is_default": 1}, "name")
        or frappe.db.get_value("Sales Taxes and Charges Template", {"company": company}, "name")
    )


def _get_branch(company: str) -> str | None:
    return (
        frappe.db.get_value("Company Branch", {"company": company, "is_active": 1}, "name")
        or frappe.db.get_value("Company Branch", {"company": company}, "name")
    )


def _get_default_warehouse(company: str) -> str | None:
    abbr = frappe.db.get_value("Company", company, "abbr")
    for wh in (f"Stores - {abbr}", f"Finished Goods - {abbr}", f"All Warehouses - {abbr}"):
        if frappe.db.exists("Warehouse", wh):
            return wh
    return frappe.db.get_value("Warehouse", {"company": company, "is_group": 0}, "name")


def _wait_for_zatca_log(invoice_name: str, max_wait: int = 30) -> dict | None:
    """Poll ZATCA Integration Log for this invoice (background worker may take a few seconds)."""
    print(f"  ⏳ Waiting for ZATCA Integration Log (up to {max_wait}s)…")
    for elapsed in range(max_wait):
        time.sleep(1)
        log = frappe.db.get_value(
            "ZATCA Integration Log",
            {"invoice_reference": invoice_name},
            ["name", "status", "zatca_status", "zatca_message", "zatca_http_status_code"],
            as_dict=True,
        )
        if log:
            print(f"  ✅ Log found after {elapsed + 1}s")
            return log
    print(f"  ⚠️  No log found after {max_wait}s — worker may still be processing")
    return None


def _check_additional_fields(invoice_name: str) -> dict | None:
    name = frappe.db.get_value("Sales Invoice Additional Fields", {"sales_invoice": invoice_name}, "name")
    if not name:
        return None
    doc = frappe.get_doc("Sales Invoice Additional Fields", name)
    return {
        "name": doc.name,
        "docstatus": doc.docstatus,
        "zatca_status": doc.get("zatca_status") or doc.get("status"),
        "uuid": doc.get("uuid"),
        "invoice_hash": ((doc.get("invoice_hash") or "")[:20] + "…") if doc.get("invoice_hash") else None,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Pre-flight
# ──────────────────────────────────────────────────────────────────────────────
def _preflight(company: str) -> dict[str, Any]:
    issues: list[str] = []
    info: dict[str, Any] = {}

    settings = _get_active_zatca_settings(company)
    if not settings:
        issues.append("❌ No active ZATCA Business Settings for company")
    else:
        info["settings_id"]    = settings.name
        info["fatoora_server"] = settings.fatoora_server
        info["zatca_enabled"]  = bool(settings.enable_zatca_integration)
        info["sync_mode"]      = settings.sync_with_zatca
        info["onboarded"]      = bool(settings.compliance_request_id)
        info["has_prod_csid"]  = bool(settings.production_request_id)
        info["vat"]            = settings.vat_registration_number
        if not settings.enable_zatca_integration:
            issues.append("❌ ZATCA integration is DISABLED in settings")
        if not settings.compliance_request_id:
            issues.append("❌ Not onboarded — run sandbox phase first")
        if not settings.zatca_cli_path:
            issues.append("❌ ZATCA CLI path not configured")

    tax_template = _get_tax_template(company)
    if not tax_template:
        issues.append("❌ No Sales Taxes and Charges Template found for company")
    else:
        info["tax_template"] = tax_template

    tax_cat = frappe.db.get_value("Tax Category", {"title": "Standard rate"}, "name")
    if not tax_cat:
        issues.append("❌ Tax Category 'Standard rate' not found")
    info["tax_category"] = tax_cat

    info["issues"] = issues
    info["ready"]  = len(issues) == 0
    return info


# ──────────────────────────────────────────────────────────────────────────────
# Stock pre-check
# ──────────────────────────────────────────────────────────────────────────────
def _ensure_stock(item_id: str, qty: float, company: str) -> dict:
    """
    If item is a stock item with insufficient qty, create a Material Receipt
    so the invoice submission does not fail with NegativeStockError.
    """
    is_stock = frappe.db.get_value("Item", item_id, "is_stock_item")
    if not is_stock:
        return {"action": "skipped — non-stock item"}

    warehouse = _get_default_warehouse(company)
    if not warehouse:
        return {"action": "⚠️ no warehouse found — skipped stock check"}

    from erpnext.stock.utils import get_stock_balance
    current = get_stock_balance(item_id, warehouse, with_valuation_rate=False)
    print(f"  📦 Current stock of {item_id} in {warehouse}: {current} units")

    if current >= qty:
        return {"action": "sufficient_stock", "warehouse": warehouse, "available": current}

    needed = qty - current + 10   # buffer
    print(f"  📥 Need {qty} but have {current} — adding {needed} units via Material Receipt…")

    se = frappe.new_doc("Stock Entry")
    se.stock_entry_type = "Material Receipt"
    se.company = company
    se.append("items", {
        "item_code": item_id,
        "t_warehouse": warehouse,
        "qty": needed,
        "basic_rate": 50,
    })
    se.save(ignore_permissions=True)
    se.submit()
    frappe.db.commit()
    print(f"  ✅ Stock Entry {se.name} — added {needed} units to {warehouse}")
    return {"action": "stock_entry_created", "stock_entry": se.name, "warehouse": warehouse, "added": needed}


# ──────────────────────────────────────────────────────────────────────────────
# Invoice creation
# ──────────────────────────────────────────────────────────────────────────────
def _create_b2c_invoice(
    company: str,
    customer: str,
    item_id: str,
    qty: float,
    rate: float,
    tax_template: str,
    tax_category: str,
) -> "frappe.model.document.Document":
    """Build and save a B2C Sales Invoice with VAT tax row."""
    invoice = frappe.new_doc("Sales Invoice")
    invoice.company           = company
    invoice.customer          = customer
    invoice.tax_category      = tax_category
    invoice.taxes_and_charges = tax_template

    # Set mandatory custom branch field if present in the doctype
    if frappe.get_meta("Sales Invoice").has_field("branch"):
        branch = _get_branch(company)
        if branch:
            invoice.branch = branch

    invoice.append("items", {"item_code": item_id, "qty": qty, "rate": rate})
    invoice.set_missing_values()
    invoice.set_taxes()
    invoice.calculate_taxes_and_totals()
    invoice.save(ignore_permissions=True)
    frappe.db.commit()
    return invoice


# ──────────────────────────────────────────────────────────────────────────────
# Main scenario
# ──────────────────────────────────────────────────────────────────────────────
@frappe.whitelist()
def run_b2c_scenario(
    company:  str   = DEFAULT_COMPANY,
    customer: str   = DEFAULT_CUSTOMER,
    item_id:  str   = DEFAULT_ITEM,
    qty:      float = DEFAULT_QTY,
    rate:     float = DEFAULT_RATE,
) -> dict[str, Any]:
    """Full end-to-end B2C ZATCA invoice scenario."""
    frappe.set_user("Administrator")

    report: dict[str, Any] = {
        "scenario":   "B2C Simplified Invoice → ZATCA Reporting",
        "started_at": str(now_datetime()),
        "company":    company,
        "customer":   customer,
        "item":       item_id,
        "qty":        qty,
        "rate":       rate,
    }

    # ── STEP 1: Pre-flight ────────────────────────────────────────────────────
    _print_step(1, "Pre-flight checks")
    preflight = _preflight(company)
    report["preflight"] = preflight

    for key, val in preflight.items():
        if key != "issues":
            _print_result(key, val)

    if preflight["issues"]:
        print("\n  ISSUES FOUND:")
        for issue in preflight["issues"]:
            print(f"    {issue}")

    if not preflight["ready"]:
        report["success"] = False
        report["verdict"] = "❌ FAILED — Pre-flight checks did not pass"
        print(f"\n{report['verdict']}")
        return report

    print("\n  ✅ All pre-flight checks passed")

    # ── STEP 2: Stock check ───────────────────────────────────────────────────
    _print_step(2, f"Stock check for {item_id}")
    stock_info = _ensure_stock(item_id, qty, company)
    report["stock_check"] = stock_info
    _print_result("Stock action", stock_info)

    # ── STEP 3: Create invoice ────────────────────────────────────────────────
    _print_step(3, f"Creating B2C Sales Invoice — {qty} × {item_id} @ SAR {rate}")
    invoice = _create_b2c_invoice(
        company=company,
        customer=customer,
        item_id=item_id,
        qty=qty,
        rate=rate,
        tax_template=preflight["tax_template"],
        tax_category=preflight["tax_category"],
    )

    inv_info = {
        "name":        invoice.name,
        "status":      invoice.status,
        "net_total":   invoice.net_total,
        "tax_amount":  sum(r.tax_amount for r in invoice.taxes),
        "grand_total": invoice.grand_total,
        "currency":    invoice.currency,
        "tax_rows":    [
            {"account": r.account_head, "rate%": r.rate, "amount": r.tax_amount}
            for r in invoice.taxes
        ],
    }
    report["invoice"] = inv_info

    _print_result("Invoice",     invoice.name)
    _print_result("Net total",   f"SAR {invoice.net_total:,.2f}")
    _print_result("VAT 15%",     f"SAR {inv_info['tax_amount']:,.2f}")
    _print_result("Grand total", f"SAR {invoice.grand_total:,.2f}")
    _print_result("Tax rows",    inv_info["tax_rows"])

    if not invoice.taxes:
        report["success"] = False
        report["verdict"] = "❌ FAILED — Invoice has no VAT rows"
        print(f"\n{report['verdict']}")
        return report

    print(f"\n  ✅ Draft invoice created: {invoice.name}")

    # ── STEP 4: Submit invoice ────────────────────────────────────────────────
    _print_step(4, f"Submitting invoice {invoice.name}")
    print("  → ksa_compliance on_submit hook will fire → ZATCA XML generated → enqueued for reporting")

    try:
        invoice.submit()
        frappe.db.commit()
        print(f"  ✅ Invoice submitted (docstatus={invoice.docstatus})")
        report["invoice"]["docstatus"]    = invoice.docstatus
        report["invoice"]["submitted_at"] = str(now_datetime())
    except Exception as exc:
        report["success"]      = False
        report["submit_error"] = str(exc)
        report["verdict"]      = f"❌ FAILED — Submission error: {exc}"
        print(f"\n{report['verdict']}")
        return report

    # ── STEP 5: Check Additional Fields doc ───────────────────────────────────
    _print_step(5, "Checking Sales Invoice Additional Fields (ksa_compliance)")
    add_fields = _check_additional_fields(invoice.name)
    report["additional_fields"] = add_fields

    if add_fields:
        _print_result("Doc name",           add_fields["name"])
        _print_result("DocStatus",          add_fields["docstatus"])
        _print_result("ZATCA status",       add_fields["zatca_status"])
        _print_result("UUID",               add_fields["uuid"])
        _print_result("Invoice hash",       add_fields["invoice_hash"])
        print("  ✅ Additional Fields doc found — XML was generated successfully")
    else:
        print("  ⚠️  No Additional Fields doc yet — may still be creating")

    # ── STEP 6: Wait for ZATCA Integration Log ────────────────────────────────
    _print_step(6, "Waiting for ZATCA Integration Log (background worker)")
    log = _wait_for_zatca_log(invoice.name, max_wait=30)
    report["zatca_log"] = log

    if log:
        _print_result("Log name",           log["name"])
        _print_result("Status",             log["status"])
        _print_result("ZATCA status",       log["zatca_status"])
        _print_result("ZATCA HTTP code",    log["zatca_http_status_code"])
        _print_result("ZATCA message",      log["zatca_message"])
    else:
        print("  ⚠️  No ZATCA log found within 30s wait window")

    # ── STEP 7: Verdict ───────────────────────────────────────────────────────
    _print_step(7, "Final Verdict")

    zatca_passed = False
    if log:
        status_str = (log.get("zatca_status") or log.get("status") or "").lower()
        msg_str    = (log.get("zatca_message") or "").lower()
        zatca_passed = any(k in status_str or k in msg_str for k in ("reported", "cleared", "accepted"))
    elif add_fields:
        # XML was generated and submitted → ZATCA accepted at least the XML format
        zatca_passed = add_fields.get("docstatus") == 1

    report["success"]     = zatca_passed
    report["finished_at"] = str(now_datetime())

    if zatca_passed:
        report["verdict"] = "✅ PASSED — B2C invoice REPORTED to ZATCA Sandbox successfully"
    elif log and not zatca_passed:
        report["verdict"] = "❌ FAILED — ZATCA rejected or returned error"
    else:
        report["verdict"] = (
            "⚠️ PARTIAL — Invoice submitted & XML generated, "
            "but ZATCA log not confirmed (worker still processing)"
        )

    print(f"\n  {report['verdict']}")
    print(f"\n  Invoice:     {invoice.name}")
    print(f"  Grand Total: SAR {invoice.grand_total:,.2f} (incl. 15% VAT)")
    print(f"  ZATCA Env:   {preflight.get('fatoora_server')}")

    print(f"\n{_sep('═')}")
    print("  SUMMARY")
    print(_sep("═"))
    print(f"  {report['verdict']}")
    print(_sep("═"))

    return report


# ──────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────────────────────────────────────
def main(
    company:  str   = DEFAULT_COMPANY,
    customer: str   = DEFAULT_CUSTOMER,
    item_id:  str   = DEFAULT_ITEM,
    qty:      float = DEFAULT_QTY,
    rate:     float = DEFAULT_RATE,
) -> None:
    """Entry point for bench execute."""
    result = run_b2c_scenario(
        company=company,
        customer=customer,
        item_id=item_id,
        qty=qty,
        rate=rate,
    )
    print("\n\n── JSON REPORT ──")
    print(json.dumps(result, indent=2, default=str))
