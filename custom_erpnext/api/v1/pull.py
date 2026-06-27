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
	validate_warehouse_access,
)
from custom_erpnext.services.branch_permission_service import (
	bypass_branch_restrictions,
	get_user_branches,
	user_has_branch_access,
)
from custom_erpnext.services import pull_service


def _resolve_branch_scope(branch):
	"""Resolve the effective branch filter for an optional-``branch`` read.

	Prevents cross-branch data exposure when a branch-scoped consumer omits the
	``branch`` parameter. Returns ``(scope, deny)`` where:

	  * ``scope`` is the validated branch (when provided), ``None`` when the
	    caller may read across all branches (bypass role), or the caller's list
	    of allowed branches otherwise.
	  * ``deny`` is ``True`` when a restricted caller has no branch access at all,
	    signalling the endpoint to return an empty result set.
	"""
	if branch:
		validate_branch_access(branch)
		return branch, False
	if bypass_branch_restrictions():
		return None, False
	allowed = get_user_branches()
	if not allowed:
		return None, True
	return allowed, False


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
def pull_item_groups(group_type=None, modified_from=None, page=1, page_size=100):
	if group_type and group_type not in ("Main Group", "Sub Group"):
		frappe.throw("group_type must be 'Main Group' or 'Sub Group'")
	page, page_size = validate_pagination(page, page_size)
	records, total = pull_service.pull_item_groups(group_type, modified_from, page, page_size)
	return success({"item_groups": records}, meta=paginated_meta(page, page_size, total))


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
	branch_scope, deny = _resolve_branch_scope(branch)
	page, page_size = validate_pagination(page, page_size)
	if deny:
		return success({"customers": []}, meta=paginated_meta(page, page_size, 0))
	records, total = pull_service.pull_customers(company, branch_scope, modified_from, page, page_size)
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
	branch_scope, deny = _resolve_branch_scope(branch)
	page, page_size = validate_pagination(page, page_size)
	if deny:
		return success({"warehouses": []}, meta=paginated_meta(page, page_size, 0))
	records, total = pull_service.pull_warehouses(company, branch_scope, modified_from, page, page_size)
	return success({"warehouses": records}, meta=paginated_meta(page, page_size, total))


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@middleware_api
def pull_stock(warehouse=None, branch=None, modified_from=None, page=1, page_size=200):
	if branch:
		validate_branch_access(branch)
	# Close the warehouse IDOR: an explicit warehouse must belong to a branch the
	# caller can access, otherwise stock for any branch is readable via warehouse=.
	validate_warehouse_access(warehouse)
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
def pull_discounts(branch=None, modified_from=None, page=1, page_size=100):
	if branch:
		validate_branch_access(branch)
	page, page_size = validate_pagination(page, page_size)
	records, total, pos_profile_discounts = pull_service.pull_discounts(
		branch, modified_from, page, page_size
	)
	return success(
		{"discounts": records, "pos_profile_discounts": pos_profile_discounts},
		meta=paginated_meta(page, page_size, total),
	)


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@middleware_api
def pull_employees(company=None, branch=None, modified_from=None, page=1, page_size=100):
	if company:
		validate_company(company)
	branch_scope, deny = _resolve_branch_scope(branch)
	page, page_size = validate_pagination(page, page_size)
	if deny:
		return success({"employees": []}, meta=paginated_meta(page, page_size, 0))
	records, total = pull_service.pull_employees(company, branch_scope, modified_from, page, page_size)
	return success({"employees": records}, meta=paginated_meta(page, page_size, total))


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@middleware_api
def pull_pos_devices(branch=None, modified_from=None):
	branch_scope, deny = _resolve_branch_scope(branch)
	if deny:
		return success({"pos_devices": []}, meta={"count": 0})

	filters = {"is_active": 1}
	if branch_scope is not None:
		filters["branch"] = branch_scope if isinstance(branch_scope, str) else ["in", branch_scope]
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


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@middleware_api
def pull_system_settings(branch=None, company=None, modified_from=None):
	if branch:
		validate_branch_access(branch)
	if company:
		validate_company(company)
	settings = pull_service.pull_system_settings(branch=branch, company=company, modified_from=modified_from)
	return success({"settings": settings}, meta={"branch": branch, "company": company})


# POST-only: full_sync writes a checkpoint (Sync Configuration.last_sync_time),
# so it must not be reachable as a GET-safe/cacheable method (SEC-09).
@frappe.whitelist(allow_guest=True, methods=["POST"])
@middleware_api
def full_sync(branch=None, price_list=None, page=1, page_size=500):
	if not branch:
		frappe.throw("branch is required for full_sync")
	validate_branch_access(branch)
	page, page_size = validate_pagination(page, page_size, max_page_size=1000)

	data = pull_service.full_sync(branch=branch, price_list=price_list, page=page, page_size=page_size)
	totals = data.pop("totals", {})
	page = data.pop("page")
	page_size = data.pop("page_size")

	if frappe.db.exists("Sync Configuration", "Full Sync Day Open"):
		frappe.db.set_value(
			"Sync Configuration",
			"Full Sync Day Open",
			"last_sync_time",
			frappe.utils.now_datetime(),
			update_modified=False,
		)

	max_total = max(totals.values()) if totals else 0
	return success(
		data,
		meta={
			**paginated_meta(page, page_size, max_total),
			"totals": totals,
			"sync_type": "full",
		},
	)


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@middleware_api
def pull_cashier_shifts(
	branch=None,
	pos_device=None,
	status=None,
	modified_from=None,
	include_movements=0,
	page=1,
	page_size=50,
):
	branch_scope, deny = _resolve_branch_scope(branch)
	page, page_size = validate_pagination(page, page_size, max_page_size=200)
	if deny:
		return success({"shifts": []}, meta=paginated_meta(page, page_size, 0))

	from custom_erpnext.services.cashier_shift_service import pull_cashier_shifts as pull_shifts

	records, total = pull_shifts(
		branch=branch_scope,
		pos_device=pos_device,
		status=status,
		modified_from=modified_from,
		include_movements=include_movements,
		page=page,
		page_size=page_size,
	)
	return success({"shifts": records}, meta=paginated_meta(page, page_size, total))


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@middleware_api
def get_sales_invoice_zatca_status(sales_invoice=None, offline_invoice_id=None, request_id=None):
	from custom_erpnext.integrations.zatca.utils import get_zatca_payload_for_invoice

	if not sales_invoice and offline_invoice_id:
		from custom_erpnext.services.sales_invoice_sync_service import find_invoice_by_sync_key

		sales_invoice = find_invoice_by_sync_key(offline_invoice_id)

	if not sales_invoice:
		frappe.throw("sales_invoice or offline_invoice_id is required")

	invoice = frappe.db.get_value(
		"Sales Invoice", sales_invoice, ["name", "branch"], as_dict=True
	)

	# Enforce branch ownership: a middleware consumer must not read the ZATCA
	# payload (totals, QR, buyer tax IDs) of an invoice outside its branches.
	# Restricted callers get one uniform response whether the invoice is missing
	# or simply out of scope, so invoice ids cannot be enumerated (SEC-02/SEC-10).
	if bypass_branch_restrictions():
		if not invoice:
			frappe.throw(f"Sales Invoice {sales_invoice} not found")
	elif (
		not invoice
		or not invoice.branch
		or not user_has_branch_access(frappe.session.user, invoice.branch)
	):
		frappe.throw(
			f"Not permitted to access Sales Invoice {sales_invoice}",
			frappe.PermissionError,
		)

	return success(
		get_zatca_payload_for_invoice(invoice.name),
		meta={"request_id": request_id},
	)
