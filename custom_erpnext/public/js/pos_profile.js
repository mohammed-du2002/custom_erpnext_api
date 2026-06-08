// Copyright (c) 2026, mohammed-du and contributors

frappe.ui.form.on("POS Profile", {
	branch(frm) {
		if (frm.doc.branch) {
			frappe.db.get_value("Company Branch", frm.doc.branch, "company", (r) => {
				if (r.company && frm.doc.company !== r.company) {
					frm.set_value("company", r.company);
				}
			});
		}
	},

	default_cashier(frm) {
		custom_erpnext.pos_profile.validate_user_branch(frm, frm.doc.default_cashier);
	},

	validate(frm) {
		if (frm.doc.default_cashier && frm.doc.branch) {
			custom_erpnext.pos_profile.validate_user_branch_sync(frm, frm.doc.default_cashier);
		}
	},
});

frappe.ui.form.on("POS Profile User", {
	user(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.user && frm.doc.branch) {
			custom_erpnext.pos_profile.validate_user_branch(frm, row.user, true);
		}
	},
});

frappe.provide("custom_erpnext.pos_profile");

custom_erpnext.pos_profile.validate_user_branch_sync = function (frm, user) {
	frappe.call({
		method: "custom_erpnext.api.client.validate_user_branch_access",
		args: { user, branch: frm.doc.branch },
		async: false,
		callback(r) {
			const result = r.message || {};
			if (!result.allowed) {
				frappe.throw(result.message || __("User is not assigned to this branch"));
			}
		},
	});
};

custom_erpnext.pos_profile.validate_user_branch = function (frm, user, silent = false) {
	if (!frm.doc.branch || !user) return true;

	return frappe
		.call({
			method: "custom_erpnext.api.client.validate_user_branch_access",
			args: { user, branch: frm.doc.branch },
			async: false,
		})
		.then((r) => {
			const result = r.message || {};
			if (!result.allowed) {
				if (!silent) {
					frappe.msgprint({
						title: __("Branch Access Denied"),
						message: result.message,
						indicator: "red",
					});
					frappe.validated = false;
				}
				return false;
			}
			return true;
		});
};
