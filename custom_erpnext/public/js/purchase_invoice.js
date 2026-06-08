// Copyright (c) 2026, mohammed-du and contributors

frappe.ui.form.on("Purchase Invoice", {
	refresh(frm) {
		custom_erpnext.purchase_invoice.calculate_retail_amounts(frm);
	},

	retail_tax_rate(frm) {
		custom_erpnext.purchase_invoice.calculate_retail_tax(frm);
	},

	net_total(frm) {
		custom_erpnext.purchase_invoice.calculate_retail_tax(frm);
	},

	validate(frm) {
		custom_erpnext.purchase_invoice.calculate_retail_amounts(frm);
	},
});

frappe.ui.form.on("Purchase Invoice Addon", {
	amount(frm) {
		custom_erpnext.purchase_invoice.calculate_addon_totals(frm);
	},

	percentage(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.is_percentage) {
			custom_erpnext.purchase_invoice.calculate_addon_row(frm, row);
		}
		custom_erpnext.purchase_invoice.calculate_addon_totals(frm);
	},

	is_percentage(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		custom_erpnext.purchase_invoice.calculate_addon_row(frm, row);
		custom_erpnext.purchase_invoice.calculate_addon_totals(frm);
	},

	addons_remove(frm) {
		custom_erpnext.purchase_invoice.calculate_addon_totals(frm);
	},
});

frappe.provide("custom_erpnext.purchase_invoice");

custom_erpnext.purchase_invoice.calculate_retail_tax = function (frm) {
	const base = flt(frm.doc.net_total) || flt(frm.doc.base_net_total);
	const rate = flt(frm.doc.retail_tax_rate);

	if (base && rate) {
		frm.set_value("retail_tax_amount", (base * rate) / 100);
	}
};

custom_erpnext.purchase_invoice.calculate_addon_row = function (frm, row) {
	if (!row.is_percentage) return;

	const base = flt(frm.doc.net_total) || flt(frm.doc.base_net_total);
	const pct = flt(row.percentage);

	if (base && pct) {
		frappe.model.set_value(row.doctype, row.name, "amount", (base * pct) / 100);
	}
};

custom_erpnext.purchase_invoice.calculate_addon_totals = function (frm) {
	let addon_total = 0;

	(frm.doc.addons || []).forEach((row) => {
		custom_erpnext.purchase_invoice.calculate_addon_row(frm, row);
		addon_total += flt(row.amount);
	});

	frm.doc.__addon_total = addon_total;
};

custom_erpnext.purchase_invoice.calculate_retail_amounts = function (frm) {
	custom_erpnext.purchase_invoice.calculate_retail_tax(frm);
	custom_erpnext.purchase_invoice.calculate_addon_totals(frm);
};
