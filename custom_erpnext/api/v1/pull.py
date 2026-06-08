# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe

from custom_erpnext.api.auth import middleware_api
from custom_erpnext.api.response import paginated_meta, success
from custom_erpnext.api.validators import (
	validate_branch,
	validate_branch_access,
	validate_company,
	validate_pagination,
)
from custom_erpnext.services.branch_permission_service import bypass_branch_restrictions, get_user_branches
from custom_erpnext.services import pull_service


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@middleware_api
def health_check():
	erpnext_version = None
	try:
		import erpnext

		erpnext_version = erpnext.__version__
	except Exception:
		pass

	return success(
		{
			"status": "ok",
			"site": frappe.local.site,
			"erpnext_version": erpnext_version,
		},
		meta={"request_id": getattr(frappe.local, "middleware_request_id", None)},
	)


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@middleware_api
def get_items_for_pos(branch=None, modified_from=None, page=1, page_size=100, price_list=None):
	validate_branch_access(branch)
	page, page_size = validate_pagination(page, page_size, max_page_size=500)

	items, total, context = pull_service.fetch_items_for_pos(
		branch=branch,
		modified_from=modified_from,
		page=page,
		page_size=page_size,
		price_list=price_list,
	)

	return success(
		{"items": items, "context": context},
		meta=paginated_meta(page, page_size, total),
	)


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@middleware_api
def pull_items(modified_from=None, page=1, page_size=100):
	page, page_size = validate_pagination(page, page_size)
	records, total = pull_service.pull_items(modified_from, page, page_size)
	return success({"items": records}, meta=paginated_meta(page, page_size, total))


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@middleware_api
def pull_item_prices(company=None, modified_from=None, page=1, page_size=200):
	if company:
		validate_company(company)
	page, page_size = validate_pagination(page, page_size, max_page_size=1000)
	records, total = pull_service.pull_item_prices(company, modified_from, page, page_size)
	return success({"prices": records}, meta=paginated_meta(page, page_size, total))


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@middleware_api
def pull_customers(company=None, branch=None, modified_from=None, page=1, page_size=100):
	if branch:
		validate_branch_access(branch)
	page, page_size = validate_pagination(page, page_size)
	records, total = pull_service.pull_customers(company, branch, modified_from, page, page_size)
	return success({"customers": records}, meta=paginated_meta(page, page_size, total))


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@middleware_api
def pull_tax_templates(modified_from=None, page=1, page_size=50):
	page, page_size = validate_pagination(page, page_size)
	records, total = pull_service.pull_tax_templates(modified_from, page, page_size)
	return success({"tax_templates": records}, meta=paginated_meta(page, page_size, total))


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@middleware_api
def pull_warehouses(company=None, branch=None, modified_from=None, page=1, page_size=50):
	if company:
		validate_company(company)
	if branch:
		validate_branch_access(branch)
	page, page_size = validate_pagination(page, page_size)
	records, total = pull_service.pull_warehouses(company, branch, modified_from, page, page_size)
	return success({"warehouses": records}, meta=paginated_meta(page, page_size, total))


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@middleware_api
def pull_stock(warehouse=None, branch=None, modified_from=None, page=1, page_size=200):
	if branch:
		validate_branch_access(branch)
	page, page_size = validate_pagination(page, page_size, max_page_size=1000)
	records, total, warehouse_name = pull_service.pull_stock(
		warehouse, branch, modified_from, page, page_size
	)
	return success(
		{"stock": records, "warehouse": warehouse_name},
		meta=paginated_meta(page, page_size, total),
	)


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@middleware_api
def pull_promotions(branch=None, modified_from=None, page=1, page_size=50):
	if branch:
		validate_branch_access(branch)
	page, page_size = validate_pagination(page, page_size)
	records, total = pull_service.pull_promotions(branch, modified_from, page, page_size)
	return success({"promotions": records}, meta=paginated_meta(page, page_size, total))


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@middleware_api
def pull_branches(company=None, modified_from=None):
	if company:
		validate_company(company)
	records = pull_service.pull_branches(company, modified_from)
	if not bypass_branch_restrictions():
		allowed = set(get_user_branches())
		records = [row for row in records if row.get("branch") in allowed]
	return success({"branches": records}, meta={"count": len(records)})


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@middleware_api
def pull_pos_devices(branch=None, modified_from=None):
	filters = {"is_active": 1}
	if branch:
		validate_branch_access(branch)
		filters["branch"] = branch
	if modified_from:
		filters.update(pull_service.get_modified_filter(modified_from))

	records = frappe.get_all(
		"POS Device",
		filters=filters,
		fields=[
			"name",
			"device_id",
			"device_name",
			"branch",
			"warehouse",
			"pos_profile",
			"device_type",
			"last_sync_time",
			"is_online",
			"modified",
		],
		order_by="modified asc",
	)
	return success({"pos_devices": records}, meta={"count": len(records)})
