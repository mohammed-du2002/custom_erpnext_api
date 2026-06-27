# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime, now_datetime

from custom_erpnext.services.cashier_movement_gl_service import maybe_post_movement_gl
from custom_erpnext.services.cashier_shift_service import link_shift_to_daily_sales_summary
from custom_erpnext.services.sales_invoice_sync_service import middleware_sync_context


BATCH_ENQUEUE_THRESHOLD = 20
MAX_BATCH_SIZE = 50
DATETIME_SKEW_SECONDS = 300
DEFAULT_APPROVAL_THRESHOLD = 0

MOVEMENT_TYPES = {
	"Shift Open": {"direction": "Neutral", "requires_open_shift": False, "requires_reason": False},
	"Shift Close": {"direction": "Neutral", "requires_open_shift": True, "requires_reason": False},
	"Cash In": {"direction": "In", "requires_open_shift": True, "requires_reason": False},
	"Cash Out": {"direction": "Out", "requires_open_shift": True, "requires_reason": True},
	"Safe Drop": {"direction": "Out", "requires_open_shift": True, "requires_reason": False},
	"Petty Cash": {"direction": "Out", "requires_open_shift": True, "requires_reason": True},
	"Float Adjustment": {
		"direction": None,
		"requires_open_shift": True,
		"requires_reason": True,
		"requires_explicit_direction": True,
	},
	"Bank Deposit": {"direction": "Out", "requires_open_shift": True, "requires_reason": False},
	"Change Fund": {
		"direction": None,
		"requires_open_shift": True,
		"requires_reason": True,
		"requires_explicit_direction": True,
	},
}

VARIABLE_DIRECTION_TYPES = {"Float Adjustment", "Change Fund"}


def sync_cashier_movements(movements, request_id=None):
	if not movements:
		frappe.throw(_("movements list is required"))

	if len(movements) > MAX_BATCH_SIZE:
		frappe.throw(_("Maximum {0} movements per request").format(MAX_BATCH_SIZE))

	_validate_batch_ids(movements)

	if len(movements) > BATCH_ENQUEUE_THRESHOLD:
		job_id = f"cashier-movements-{request_id}" if request_id else None
		job = frappe.enqueue(
			"custom_erpnext.services.cashier_movement_sync_service.process_movement_batch",
			queue="long",
			movements=movements,
			request_id=request_id,
			timeout=1800,
			job_id=job_id,
			deduplicate=True,
		)
		return {
			"queued": True,
			"count": len(movements),
			"job_id": getattr(job, "id", None),
			"message": "Batch queued for processing",
		}

	return process_movement_batch(movements, request_id=request_id)


def process_movement_batch(movements, request_id=None):
	results = []
	success_count = 0
	failed_count = 0

	with middleware_sync_context():
		for data in sorted(movements, key=lambda row: row.get("movement_datetime") or ""):
			try:
				result = create_or_update_cashier_movement(data, request_id=request_id)
				results.append(result)
				if result.get("status") == "success":
					success_count += 1
				else:
					failed_count += 1
			except Exception as err:
				frappe.log_error(
					title="Cashier Movement Sync Failed",
					message=(
						f"offline_movement_id={data.get('offline_movement_id')} "
						f"request_id={request_id}\n\n{frappe.get_traceback()}"
					),
				)
				results.append(
					{
						"offline_movement_id": data.get("offline_movement_id"),
						"status": "failed",
						"error": str(err),
					}
				)
				failed_count += 1

		if not frappe.flags.in_test:
			frappe.db.commit()

	return {
		"queued": False,
		"total": len(movements),
		"success_count": success_count,
		"failed_count": failed_count,
		"results": results,
	}


def create_or_update_cashier_movement(data, request_id=None):
	offline_id = data.get("offline_movement_id")
	if not offline_id:
		frappe.throw(_("offline_movement_id is required"))

	existing = frappe.db.get_value(
		"Cashier Movement",
		{"offline_movement_id": offline_id},
		["name", "pos_cashier_shift", "sync_status", "journal_entry"],
		as_dict=True,
	)
	if existing:
		return _movement_result(
			offline_id,
			existing.name,
			existing.pos_cashier_shift,
			idempotent=True,
			sync_status=existing.sync_status or "Synced",
			journal_entry=existing.journal_entry,
		)

	if not _has_full_movement_payload(data):
		frappe.throw(
			_("Cashier Movement not found for offline_movement_id {0}").format(offline_id)
		)

	_validate_movement_payload(data)
	shift = _get_or_create_shift_for_movement(data)

	movement = frappe.new_doc("Cashier Movement")
	_map_movement_fields(movement, data, shift.name, request_id)

	from custom_erpnext.services.naming_series_service import apply_branch_naming_series

	apply_branch_naming_series(movement)
	movement.flags.ignore_permissions = True
	movement.insert()

	shift = _update_shift_from_movement(shift, movement, data)
	journal_entry = maybe_post_movement_gl(shift, movement, data)
	_log_movement_activity(movement)

	return _movement_result(
		offline_id,
		movement.name,
		shift.name,
		idempotent=False,
		sync_status="Synced",
		journal_entry=journal_entry,
	)


def _has_full_movement_payload(data):
	required = [
		"movement_type",
		"company",
		"branch",
		"pos_device",
		"cashier",
		"offline_shift_id",
		"movement_datetime",
	]
	return all(data.get(field) for field in required)


def _validate_batch_ids(movements):
	seen = set()
	for row in movements:
		offline_id = row.get("offline_movement_id")
		if not offline_id:
			frappe.throw(_("offline_movement_id is required for each movement"))
		if offline_id in seen:
			frappe.throw(_("Duplicate offline_movement_id in batch: {0}").format(offline_id))
		seen.add(offline_id)


def _validate_movement_payload(data):
	movement_type = data.get("movement_type")
	if movement_type not in MOVEMENT_TYPES:
		frappe.throw(_("Invalid movement_type: {0}").format(movement_type))

	required = ["company", "branch", "pos_device", "cashier", "offline_shift_id", "movement_datetime"]
	for field in required:
		if not data.get(field):
			frappe.throw(_("{0} is required").format(field))

	from custom_erpnext.api.validators import validate_branch_access

	validate_branch_access(data["branch"])

	_validate_movement_datetime(data["movement_datetime"])
	_validate_company(data["company"])
	_validate_branch_company(data["company"], data["branch"])
	_validate_pos_device(data.get("pos_device"), data.get("branch"))
	_validate_cashier(data.get("cashier"))
	_validate_mode_of_payment(data.get("mode_of_payment"), data.get("company"))
	_validate_movement_amounts(data, movement_type)
	_validate_shift_state(data, movement_type)
	_validate_approval(data, movement_type)

	_resolve_offline_reference(data)


def _validate_movement_datetime(movement_datetime):
	event_time = get_datetime(movement_datetime)
	if not event_time:
		frappe.throw(_("Invalid movement_datetime: {0}").format(movement_datetime))

	latest_allowed = now_datetime() + timedelta(seconds=DATETIME_SKEW_SECONDS)
	if event_time > latest_allowed:
		frappe.throw(_("movement_datetime cannot be in the future"))


def _validate_company(company):
	if not frappe.db.exists("Company", company):
		frappe.throw(_("Company {0} not found").format(company))


def _validate_branch_company(company, branch):
	branch_company = frappe.db.get_value("Company Branch", branch, "company")
	if branch_company and branch_company != company:
		frappe.throw(_("Branch {0} does not belong to company {1}").format(branch, company))


def _validate_pos_device(device, branch):
	if not frappe.db.exists("POS Device", device):
		frappe.throw(_("POS Device {0} not found").format(device))

	device_branch = frappe.db.get_value("POS Device", device, "branch")
	if branch and device_branch and device_branch != branch:
		frappe.throw(_("POS Device {0} does not belong to branch {1}").format(device, branch))

	if not frappe.db.get_value("POS Device", device, "is_active"):
		frappe.throw(_("POS Device {0} is not active").format(device))


def _validate_cashier(cashier):
	if not frappe.db.exists("User", cashier):
		frappe.throw(_("Cashier {0} not found").format(cashier))

	if not cint(frappe.db.get_value("User", cashier, "enabled")):
		frappe.throw(_("Cashier {0} is disabled").format(cashier))

	if not cint(frappe.db.get_value("User", cashier, "pos_access")):
		frappe.throw(_("User {0} does not have POS access").format(cashier))


def _validate_mode_of_payment(mode_of_payment, company):
	if not mode_of_payment:
		return

	if not frappe.db.exists("Mode of Payment", mode_of_payment):
		frappe.throw(_("Mode of Payment {0} not found").format(mode_of_payment))

	if not frappe.db.exists("Mode of Payment Account", {"parent": mode_of_payment, "company": company}):
		frappe.throw(
			_("Mode of Payment {0} has no account configured for company {1}").format(
				mode_of_payment, company
			)
		)


def _validate_movement_amounts(data, movement_type):
	meta = MOVEMENT_TYPES[movement_type]

	if meta.get("requires_reason") and not (data.get("reason") or "").strip():
		frappe.throw(_("reason is required for movement type {0}").format(movement_type))

	if movement_type == "Shift Open":
		if data.get("opening_balance") is None:
			frappe.throw(_("opening_balance is required for Shift Open"))
		return

	if movement_type == "Shift Close":
		if data.get("closing_balance") is None:
			frappe.throw(_("closing_balance is required for Shift Close"))
		return

	if flt(data.get("amount")) <= 0:
		frappe.throw(_("amount must be greater than zero for movement type {0}").format(movement_type))

	if meta.get("requires_explicit_direction"):
		direction = (data.get("direction") or "").strip().lower()
		if direction not in ("in", "out"):
			frappe.throw(_("direction must be 'in' or 'out' for movement type {0}").format(movement_type))


def _validate_shift_state(data, movement_type):
	offline_shift_id = data["offline_shift_id"]
	shift = frappe.db.get_value(
		"POS Cashier Shift",
		{"offline_shift_id": offline_shift_id},
		["name", "status"],
		as_dict=True,
	)

	if movement_type == "Shift Open":
		if shift and shift.status in ("Open", "Closed", "Synced"):
			frappe.throw(
				_("Shift {0} already exists for offline_shift_id {1}").format(shift.name, offline_shift_id)
			)
		return

	if not shift:
		frappe.throw(_("Shift not found for offline_shift_id {0}").format(offline_shift_id))

	if movement_type == "Shift Close":
		if shift.status == "Closed":
			frappe.throw(_("Shift {0} is already closed").format(shift.name))
		return

	if shift.status != "Open":
		frappe.throw(_("Shift {0} is not open").format(shift.name))


def _validate_approval(data, movement_type):
	approved_by = data.get("approved_by")
	amount = flt(data.get("amount"))
	threshold = _get_approval_threshold(data.get("cashier"))

	if movement_type == "Float Adjustment":
		requires_approval = True
	elif threshold > 0 and amount > threshold:
		requires_approval = True
	else:
		requires_approval = False

	if not requires_approval:
		return

	if not approved_by:
		frappe.throw(_("approved_by is required for this movement"))

	if not frappe.db.exists("User", approved_by):
		frappe.throw(_("approved_by user {0} not found").format(approved_by))

	if not _is_branch_manager(approved_by, data.get("branch")):
		frappe.throw(_("approved_by user {0} is not a branch manager").format(approved_by))


def _get_approval_threshold(cashier):
	profile = frappe.db.get_value(
		"User Discount Profile",
		{"user": cashier},
		"require_approval_above",
	)
	if profile is not None:
		return flt(profile)
	return DEFAULT_APPROVAL_THRESHOLD


def _is_branch_manager(user, branch):
	if "Sales Manager" in frappe.get_roles(user) or "System Manager" in frappe.get_roles(user):
		return True

	profile = frappe.db.get_value(
		"User Discount Profile",
		{"user": user},
		["is_branch_manager", "name"],
		as_dict=True,
	)
	if profile and cint(profile.is_branch_manager):
		if not branch:
			return True
		return bool(
			frappe.db.exists(
				"User Branch Assignment",
				{"parent": profile.name, "branch": branch},
			)
		)
	return False


def _resolve_offline_reference(data):
	offline_ref = data.get("offline_reference_id")
	if not offline_ref or data.get("reference_name"):
		return

	sales_invoice = frappe.db.get_value(
		"Sales Invoice",
		{"offline_invoice_id": offline_ref},
		"name",
	)
	if sales_invoice:
		data["reference_doctype"] = "Sales Invoice"
		data["reference_name"] = sales_invoice


def _get_or_create_shift_for_movement(data):
	if data["movement_type"] != "Shift Open":
		shift_name = frappe.db.get_value(
			"POS Cashier Shift",
			{"offline_shift_id": data["offline_shift_id"]},
			"name",
		)
		return frappe.get_doc("POS Cashier Shift", shift_name)

	shift = frappe.new_doc("POS Cashier Shift")
	shift.update(
		{
			"offline_shift_id": data["offline_shift_id"],
			"shift_id": data.get("shift_id"),
			"company": data["company"],
			"branch": data["branch"],
			"pos_device": data["pos_device"],
			"cashier": data["cashier"],
			"status": "Open",
			"sync_status": "Pending",
		}
	)

	from custom_erpnext.services.naming_series_service import apply_branch_naming_series

	apply_branch_naming_series(shift)
	shift.flags.ignore_permissions = True
	shift.insert()
	return shift


def _map_movement_fields(movement, data, shift_name, request_id):
	movement_type = data["movement_type"]
	meta = MOVEMENT_TYPES[movement_type]
	direction = meta["direction"]

	if movement_type in VARIABLE_DIRECTION_TYPES:
		direction = "In" if (data.get("direction") or "").strip().lower() == "in" else "Out"

	movement.update(
		{
			"offline_movement_id": data["offline_movement_id"],
			"movement_type": movement_type,
			"movement_datetime": get_datetime(data["movement_datetime"]),
			"company": data["company"],
			"branch": data["branch"],
			"pos_device": data["pos_device"],
			"cashier": data["cashier"],
			"offline_shift_id": data["offline_shift_id"],
			"shift_id": data.get("shift_id"),
			"pos_cashier_shift": shift_name,
			"amount": abs(flt(data.get("amount"))) if data.get("amount") is not None else 0,
			"direction": direction,
			"opening_balance": flt(data.get("opening_balance")),
			"closing_balance": flt(data.get("closing_balance")),
			"mode_of_payment": data.get("mode_of_payment"),
			"reference_doctype": data.get("reference_doctype"),
			"reference_name": data.get("reference_name"),
			"offline_reference_id": data.get("offline_reference_id"),
			"reason": data.get("reason"),
			"approved_by": data.get("approved_by"),
			"remarks": data.get("remarks"),
			"sync_status": "Synced",
			"sync_log": f"Synced via middleware. request_id={request_id}",
			"request_id": request_id,
		}
	)


def _update_shift_from_movement(shift, movement, data):
	shift = frappe.get_doc("POS Cashier Shift", shift.name)
	movement_type = movement.movement_type

	if movement_type == "Shift Open":
		shift.opening_datetime = movement.movement_datetime
		shift.opening_cash = flt(data.get("opening_balance"))
		shift.expected_cash = flt(data.get("opening_balance"))
	elif movement_type == "Shift Close":
		shift.closing_datetime = movement.movement_datetime
		shift.closing_cash = flt(data.get("closing_balance"))
		shift.expected_cash = _compute_expected_cash(shift.name)
		shift.variance = flt(shift.closing_cash) - flt(shift.expected_cash)
		shift.status = "Closed"
		if data.get("daily_sales_summary"):
			shift.daily_sales_summary = data["daily_sales_summary"]
		else:
			link_shift_to_daily_sales_summary(shift, movement.movement_datetime)
	else:
		shift.expected_cash = _compute_expected_cash(shift.name)

	shift.sync_status = "Synced"
	shift.sync_time = now_datetime()
	shift.sync_log = f"Updated from {movement.name}. request_id={movement.request_id}"
	shift.flags.ignore_permissions = True
	shift.save()
	return shift


def _compute_expected_cash(shift_name):
	opening_cash = flt(frappe.db.get_value("POS Cashier Shift", shift_name, "opening_cash"))
	movements = frappe.get_all(
		"Cashier Movement",
		filters={"pos_cashier_shift": shift_name, "sync_status": "Synced"},
		fields=["movement_type", "direction", "amount"],
	)

	net = 0
	for row in movements:
		if row.movement_type in ("Shift Open", "Shift Close"):
			continue
		amount = abs(flt(row.amount))
		if row.direction == "In":
			net += amount
		elif row.direction == "Out":
			net -= amount

	return opening_cash + net


def _log_movement_activity(movement):
	from custom_erpnext.services.activity_service import log_activity

	log_activity(
		activity_type="Sync",
		user=movement.cashier,
		document_type="Cashier Movement",
		document_name=movement.name,
		description=f"{movement.movement_type}: {movement.amount or movement.opening_balance or movement.closing_balance}",
		branch=movement.branch,
		pos_device=movement.pos_device,
	)


def _movement_result(
	offline_movement_id,
	movement_name,
	shift_name,
	idempotent,
	sync_status,
	status="success",
	journal_entry=None,
):
	result = {
		"offline_movement_id": offline_movement_id,
		"cashier_movement": movement_name,
		"pos_cashier_shift": shift_name,
		"status": status,
		"idempotent": idempotent,
		"sync_status": sync_status,
	}
	if journal_entry:
		result["journal_entry"] = journal_entry
	return result
