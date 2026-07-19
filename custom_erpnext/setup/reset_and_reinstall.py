# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Root-free full site reinstall + bootstrap orchestration.

A normal ``bench reinstall`` drops and recreates the MariaDB database *and* the
database user, which requires the MariaDB **root** credentials. In environments
where root access is unavailable (only the site's own DB user is known) we can
still achieve an equivalent clean-slate reinstall:

    1. Drop every table/view inside the existing site database (site creds only).
    2. Restore the fresh framework schema into the now-empty database using the
       site DB user (``import_db_from_sql`` shells out to ``mysql`` with the site
       credentials -- no root needed).
    3. Reinstall every app in dependency-safe order.

This module is intended to be run via ``bench execute``. It is deliberately
verbose and defensive so it can be re-run safely.
"""

import frappe

# Dependency-safe install order. frappe first, then erpnext, then the apps that
# extend erpnext, with custom_erpnext (which customises everything) last.
APP_INSTALL_ORDER = ["frappe", "erpnext", "erpnext_ui", "ksa_compliance", "custom_erpnext"]


def _drop_all_objects():
	"""Drop every base table and view in the current site database."""
	frappe.db.sql("SET FOREIGN_KEY_CHECKS=0")
	rows = frappe.db.sql("SHOW FULL TABLES", as_list=True)
	dropped_tables = 0
	dropped_views = 0
	for row in rows:
		name = row[0]
		table_type = (row[1] if len(row) > 1 else "BASE TABLE") or "BASE TABLE"
		if table_type.upper() == "VIEW":
			frappe.db.sql(f"DROP VIEW IF EXISTS `{name}`")
			dropped_views += 1
		else:
			frappe.db.sql(f"DROP TABLE IF EXISTS `{name}`")
			dropped_tables += 1
	frappe.db.sql("SET FOREIGN_KEY_CHECKS=1")
	frappe.db.commit()
	return {"dropped_tables": dropped_tables, "dropped_views": dropped_views}


def reinstall_without_root(admin_password="admin"):
	"""Wipe all data and rebuild the site from scratch without MariaDB root access.

	Equivalent outcome to ``bench --site <site> reinstall`` but reuses the
	existing database and DB user instead of recreating them.
	"""
	from frappe.installer import install_app, install_db
	from frappe.utils import scheduler

	site = frappe.local.site
	conf = frappe.conf

	# Capture connection parameters *before* we tear the connection down.
	db_params = {
		"db_name": conf.db_name,
		"db_password": conf.db_password,
		"db_user": conf.get("db_user") or conf.db_name,
		"db_type": conf.get("db_type") or "mariadb",
		"db_host": conf.get("db_host"),
		"db_port": conf.get("db_port"),
		"db_socket": conf.get("db_socket"),
	}

	drop_summary = _drop_all_objects()

	# Bootstrap fresh framework schema + core tables into the empty database.
	# setup=False skips the root-only drop/create-database + create-user step.
	install_db(
		admin_password=admin_password,
		verbose=True,
		force=True,
		setup=False,
		**db_params,
	)

	installed = []
	for app in APP_INSTALL_ORDER:
		install_app(app, verbose=True, set_as_patched=True, force=False)
		installed.append(app)

	# Keep the scheduler disabled on a freshly reinstalled test site.
	scheduler.toggle_scheduler(False)
	frappe.db.commit()

	return {
		"site": site,
		"drop_summary": drop_summary,
		"installed_apps": installed,
	}


def complete_setup_wizard(
	company_name="tsc",
	company_abbr="TSC",
	country="Saudi Arabia",
	currency="SAR",
	timezone="Asia/Riyadh",
	chart_of_accounts="Standard",
	fy_start_date="2026-01-01",
	fy_end_date="2026-12-31",
	domain="Retail",
):
	"""Complete the ERPNext setup wizard programmatically (creates Company + defaults)."""
	from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

	if frappe.is_setup_complete():
		return {"status": "already-complete", "company": frappe.defaults.get_defaults().get("company")}

	args = {
		"language": "English",
		"country": country,
		"timezone": timezone,
		"currency": currency,
		"company_name": company_name,
		"company_abbr": company_abbr,
		"chart_of_accounts": chart_of_accounts,
		"fy_start_date": fy_start_date,
		"fy_end_date": fy_end_date,
		"domain": domain,
		"setup_demo": 0,
		"enable_telemetry": 0,
	}

	frappe.flags.in_setup_wizard = True
	result = setup_complete(args)
	frappe.db.commit()

	return {
		"status": result,
		"setup_complete": bool(frappe.is_setup_complete()),
		"company": frappe.db.get_value("Company", company_name, "name"),
		"default_company": frappe.db.get_single_value("Global Defaults", "default_company"),
		"currency": frappe.db.get_single_value("Global Defaults", "default_currency"),
	}


# UN/EDIFACT 4461 payment means codes required by ksa_compliance on Mode of Payment.
STANDARD_MODES_OF_PAYMENT = [
	{"mode_of_payment": "Cash", "type": "Cash", "zatca_code": "10", "account_type": "Cash"},
	{"mode_of_payment": "Credit Card", "type": "Bank", "zatca_code": "48", "account_type": "Bank"},
	{"mode_of_payment": "Debit Card", "type": "Bank", "zatca_code": "48", "account_type": "Bank"},
	{"mode_of_payment": "Cheque", "type": "Bank", "zatca_code": "20", "account_type": "Bank"},
	{"mode_of_payment": "Wire Transfer", "type": "Bank", "zatca_code": "30", "account_type": "Bank"},
	{"mode_of_payment": "Bank Draft", "type": "Bank", "zatca_code": "42", "account_type": "Bank"},
]


def ensure_modes_of_payment(company=None):
	"""Create/repair the standard Modes of Payment.

	ksa_compliance marks ``custom_zatca_payment_means_code`` mandatory (with no
	default) on Mode of Payment, which blocks ERPNext's default fixtures during the
	setup wizard. This creates the core modes with valid ZATCA codes and a company
	default account, and backfills the code on any existing mode that is missing it.
	"""
	company = company or frappe.db.get_single_value("Global Defaults", "default_company")
	created, repaired = [], []

	for spec in STANDARD_MODES_OF_PAYMENT:
		name = spec["mode_of_payment"]
		account = frappe.db.get_value(
			"Account",
			{"company": company, "account_type": spec["account_type"], "is_group": 0},
			"name",
		)

		if not frappe.db.exists("Mode of Payment", name):
			doc = frappe.get_doc(
				{
					"doctype": "Mode of Payment",
					"mode_of_payment": name,
					"enabled": 1,
					"type": spec["type"],
					"custom_zatca_payment_means_code": spec["zatca_code"],
				}
			)
			if account:
				doc.append("accounts", {"company": company, "default_account": account})
			doc.insert(ignore_permissions=True)
			created.append(name)
			continue

		doc = frappe.get_doc("Mode of Payment", name)
		changed = False
		if not doc.get("custom_zatca_payment_means_code"):
			doc.custom_zatca_payment_means_code = spec["zatca_code"]
			changed = True
		if account and not any(r.company == company for r in doc.accounts):
			doc.append("accounts", {"company": company, "default_account": account})
			changed = True
		if changed:
			doc.save(ignore_permissions=True)
			repaired.append(name)

	frappe.db.commit()
	return {"company": company, "created": created, "repaired": repaired}


def report_state():
	"""Return a snapshot of key record counts for verification."""
	doctypes = [
		"Company",
		"Fiscal Year",
		"Mode of Payment",
		"Warehouse",
		"Company Branch",
		"Item",
		"Item Price",
		"Customer",
		"POS Profile",
		"POS Device",
		"User Discount Profile",
		"Sales Invoice",
		"Sync Configuration",
		"API Integration Settings",
	]
	counts = {dt: frappe.db.count(dt) for dt in doctypes}
	return {
		"setup_complete": bool(frappe.is_setup_complete()),
		"default_company": frappe.db.get_single_value("Global Defaults", "default_company"),
		"default_currency": frappe.db.get_single_value("Global Defaults", "default_currency"),
		"counts": counts,
	}
