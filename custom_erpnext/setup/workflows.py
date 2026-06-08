# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import now_datetime


WORKFLOW_STATES = [
	{"name": "Draft", "style": ""},
	{"name": "Pending Approval", "style": "Warning"},
	{"name": "Pending", "style": "Warning"},
	{"name": "Approved", "style": "Success"},
	{"name": "Rejected", "style": "Danger"},
	{"name": "Ordered", "style": "Info"},
	{"name": "Shipped", "style": "Primary"},
	{"name": "Received", "style": "Success"},
	{"name": "Cancelled", "style": "Inverse"},
]

WORKFLOW_ACTIONS = [
	"Submit for Approval",
	"Approve",
	"Reject",
	"Reset to Draft",
	"Mark Ordered",
	"Ship",
	"Mark Received",
	"Cancel Transfer",
]


def setup_workflows():
	_ensure_workflow_states()
	_ensure_workflow_actions()
	_setup_material_request_workflow()
	_setup_stock_transfer_workflow()


def _ensure_workflow_states():
	for state in WORKFLOW_STATES:
		if not frappe.db.exists("Workflow State", state["name"]):
			doc = frappe.get_doc(
				{
					"doctype": "Workflow State",
					"workflow_state_name": state["name"],
					"style": state.get("style") or "",
				}
			)
			doc.insert(ignore_permissions=True)


def _ensure_workflow_actions():
	for action in WORKFLOW_ACTIONS:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": action}).insert(
				ignore_permissions=True
			)


def _setup_material_request_workflow():
	name = "Retail Material Request Approval"
	if frappe.db.exists("Workflow", name):
		frappe.delete_doc("Workflow", name, force=1)

	workflow = frappe.get_doc(
		{
			"doctype": "Workflow",
			"workflow_name": name,
			"document_type": "Material Request",
			"is_active": 1,
			"override_status": 0,
			"send_email_alert": 0,
			"workflow_state_field": "approval_status",
			"states": [
				_state("Draft", 0, "Stock User", "approval_status", "Draft"),
				_state("Pending Approval", 0, "Stock Manager", "approval_status", "Pending Approval"),
				_state("Approved", 0, "Purchase Manager", "approval_status", "Approved"),
				_state("Rejected", 0, "Stock User", "approval_status", "Rejected"),
				_state("Ordered", 1, "Purchase Manager", "approval_status", "Ordered"),
			],
			"transitions": [
				_transition("Draft", "Submit for Approval", "Pending Approval", "Stock User", 0),
				_transition("Pending Approval", "Approve", "Approved", "Stock Manager", 0),
				_transition("Pending Approval", "Reject", "Rejected", "Stock Manager", 0),
				_transition("Rejected", "Reset to Draft", "Draft", "Stock User", 1),
				_transition("Approved", "Mark Ordered", "Ordered", "Purchase Manager", 0),
			],
		}
	)
	workflow.insert(ignore_permissions=True)


def _setup_stock_transfer_workflow():
	name = "Retail Stock Transfer Workflow"
	if frappe.db.exists("Workflow", name):
		frappe.delete_doc("Workflow", name, force=1)

	workflow = frappe.get_doc(
		{
			"doctype": "Workflow",
			"workflow_name": name,
			"document_type": "Stock Transfer Request",
			"is_active": 1,
			"override_status": 1,
			"send_email_alert": 0,
			"workflow_state_field": "status",
			"states": [
				_state("Draft", 0, "Stock User", "status", "Draft"),
				_state("Pending", 0, "Stock Manager", "status", "Pending"),
				_state("Approved", 0, "Stock Manager", "status", "Approved"),
				_state("Rejected", 0, "Stock User", "status", "Rejected"),
				_state("Shipped", 1, "Stock User", "status", "Shipped"),
				_state("Received", 1, "Stock Manager", "status", "Received"),
				_state("Cancelled", 2, "Stock Manager", "status", "Cancelled"),
			],
			"transitions": [
				_transition("Draft", "Submit for Approval", "Pending", "Stock User", 1),
				_transition("Pending", "Approve", "Approved", "Stock Manager", 0),
				_transition("Pending", "Reject", "Rejected", "Stock Manager", 0),
				_transition("Rejected", "Reset to Draft", "Draft", "Stock User", 1),
				_transition("Approved", "Ship", "Shipped", "Stock User", 0),
				_transition("Approved", "Cancel Transfer", "Rejected", "Stock Manager", 0),
				_transition("Shipped", "Mark Received", "Received", "Stock Manager", 0),
				_transition("Shipped", "Cancel Transfer", "Cancelled", "Stock Manager", 0),
			],
		}
	)
	workflow.insert(ignore_permissions=True)


def _state(state, doc_status, role, update_field=None, update_value=None):
	return {
		"state": state,
		"doc_status": str(doc_status),
		"allow_edit": role,
		"update_field": update_field or "",
		"update_value": update_value or "",
	}


def _transition(state, action, next_state, role, allow_self_approval=1, condition=None):
	row = {
		"state": state,
		"action": action,
		"next_state": next_state,
		"allowed": role,
		"allow_self_approval": allow_self_approval,
	}
	if condition:
		row["condition"] = condition
	return row


def on_material_request_update(doc, method=None):
	if doc.approval_status == "Approved" and not doc.approved_by:
		frappe.db.set_value(doc.doctype, doc.name, "approved_by", frappe.session.user, update_modified=False)
		frappe.db.set_value(doc.doctype, doc.name, "approval_date", now_datetime(), update_modified=False)

	if doc.approval_status == "Rejected":
		frappe.db.set_value(doc.doctype, doc.name, "approved_by", frappe.session.user, update_modified=False)
		frappe.db.set_value(doc.doctype, doc.name, "approval_date", now_datetime(), update_modified=False)


def on_stock_transfer_update(doc, method=None):
	if doc.status in ("Approved", "Received") and not doc.approved_by:
		frappe.db.set_value(doc.doctype, doc.name, "approved_by", frappe.session.user, update_modified=False)
