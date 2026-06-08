// Copyright (c) 2026, mohammed-du and contributors

frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		if (frm.is_new() && !frm.doc.cashier) {
			frm.set_value("cashier", frappe.session.user);
		}
		custom_erpnext.sales_invoice.load_discount_limits(frm);
		if (frm.is_new() && frm.doc.branch) {
			custom_erpnext.sales_invoice.apply_branch_naming_series(frm);
		}
	},

	pos_device(frm) {
		if (!frm.doc.pos_device) return;

		frappe.db.get_value(
			"POS Device",
			frm.doc.pos_device,
			["branch", "warehouse", "pos_profile"],
			(r) => {
				if (r.branch && !frm.doc.branch) frm.set_value("branch", r.branch);
				if (r.warehouse && !frm.doc.set_warehouse) frm.set_value("set_warehouse", r.warehouse);
				if (r.pos_profile && !frm.doc.pos_profile) frm.set_value("pos_profile", r.pos_profile);
			}
		);
	},

	branch(frm) {
		custom_erpnext.sales_invoice.apply_branch_naming_series(frm);
	},

	is_return(frm) {
		custom_erpnext.sales_invoice.apply_branch_naming_series(frm);
	},

	cashier(frm) {
		custom_erpnext.sales_invoice.load_discount_limits(frm);
	},

	additional_discount_percentage(frm) {
		custom_erpnext.sales_invoice.validate_discount_limit(frm);
	},

	items_add(frm) {
		custom_erpnext.sales_invoice.calculate_item_discounts(frm);
	},

	validate(frm) {
		custom_erpnext.sales_invoice.calculate_item_discounts(frm);
		custom_erpnext.sales_invoice.validate_discount_limit(frm);
	},
});

frappe.ui.form.on("Sales Invoice Item", {
	discount_percentage(frm) {
		custom_erpnext.sales_invoice.calculate_item_discounts(frm);
	},

	discount_amount(frm) {
		custom_erpnext.sales_invoice.calculate_item_discounts(frm);
	},

	qty(frm) {
		custom_erpnext.sales_invoice.calculate_item_discounts(frm);
	},

	rate(frm) {
		custom_erpnext.sales_invoice.calculate_item_discounts(frm);
	},
});

frappe.provide("custom_erpnext.sales_invoice");

custom_erpnext.sales_invoice.apply_branch_naming_series = function (frm) {
	if (!frm.is_new() || !frm.doc.branch) return;

	frappe.call({
		method: "custom_erpnext.api.client.get_branch_naming_series",
		args: {
			doctype: frm.doctype,
			branch: frm.doc.branch,
			is_return: frm.doc.is_return || 0,
		},
		callback(r) {
			if (r.message && r.message.naming_series) {
				frm.set_value("naming_series", r.message.naming_series);
			}
		},
	});
};

custom_erpnext.sales_invoice.load_discount_limits = function (frm) {
	const user = frm.doc.cashier || frappe.session.user;
	frappe.call({
		method: "custom_erpnext.api.client.get_user_discount_limits",
		args: { user },
		callback(r) {
			frm.discount_limits = r.message || {};
		},
	});
};

custom_erpnext.sales_invoice.calculate_item_discounts = function (frm) {
	let total_item_discount = 0;

	(frm.doc.items || []).forEach((row) => {
		const base = flt(row.qty) * flt(row.rate);
		let row_discount = flt(row.discount_amount);

		if (!row_discount && row.discount_percentage) {
			row_discount = (base * flt(row.discount_percentage)) / 100;
		}

		total_item_discount += row_discount;
	});

	const header_discount = flt(frm.doc.discount_amount) - total_item_discount;
	if (header_discount < 0) {
		frm.set_value("discount_amount", total_item_discount);
	}
};

custom_erpnext.sales_invoice.validate_discount_limit = function (frm) {
	const limits = frm.discount_limits || {};
	const max_discount = flt(limits.max_discount_percent);
	const discount_pct = flt(frm.doc.additional_discount_percentage);
	const cashier = frm.doc.cashier || frappe.session.user;

	if (max_discount && discount_pct > max_discount) {
		if (!limits.approval_authority && !frm.doc.discount_authorized_by) {
			frappe.throw(
				__("Discount {0}% exceeds allowed limit {1}% for user {2}. Manager approval required.", [
					discount_pct,
					max_discount,
					cashier,
				])
			);
		}
	}

	(frm.doc.items || []).forEach((row) => {
		if (max_discount && flt(row.discount_percentage) > max_discount) {
			frappe.throw(
				__("Item {0}: discount {1}% exceeds limit {2}%", [
					row.item_code,
					row.discount_percentage,
					max_discount,
				])
			);
		}
	});
};
