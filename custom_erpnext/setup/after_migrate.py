# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Frappe Cloud–safe after_migrate orchestration.

Keep migrate itself short so MariaDB connections are released quickly on shared
plans. Heavy idempotent setup runs once in a single long-queue job.
"""

from __future__ import annotations

import frappe

DEFERRED_JOB_ID = "custom-erpnext-after-migrate"


def run_after_migrate():
	"""Fast path during migrate; enqueue deferred setup once."""
	from custom_erpnext.integrations.zatca.hooks import check_ksa_compliance_dependency
	from custom_erpnext.setup.laravel_integration import sync_integration_api_credentials
	from custom_erpnext.setup.sales_invoice_setup import cleanup_removed_sales_invoice_fields
	from custom_erpnext.setup.stock_settings import enable_negative_stock_for_retail

	sync_integration_api_credentials()
	cleanup_removed_sales_invoice_fields()
	enable_negative_stock_for_retail()
	check_ksa_compliance_dependency()

	frappe.enqueue(
		"custom_erpnext.setup.after_migrate.run_deferred_after_migrate",
		queue="long",
		job_id=DEFERRED_JOB_ID,
		deduplicate=True,
		enqueue_after_commit=True,
	)


def run_deferred_after_migrate():
	"""Heavy setup that must not hold connections during migrate."""
	from custom_erpnext.integrations.zatca.hooks import setup_zatca_integration
	from custom_erpnext.setup.naming_series import sync_all_branch_naming_series
	from custom_erpnext.setup.user_permissions import sync_all_user_branch_permissions
	from custom_erpnext.setup.workflows import setup_workflows

	frappe.logger("custom_erpnext").info("Starting deferred after_migrate setup")
	setup_workflows()
	sync_all_user_branch_permissions()
	sync_all_branch_naming_series()
	setup_zatca_integration()
	frappe.db.commit()
	frappe.logger("custom_erpnext").info("Deferred after_migrate setup complete")
