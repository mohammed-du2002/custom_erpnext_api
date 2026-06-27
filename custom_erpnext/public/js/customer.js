// Copyright (c) 2026, mohammed-du and contributors

frappe.ui.form.on("Customer", {
	tax_id(frm) {
		custom_erpnext.customer.sync_vat_fields(frm);
	},

	custom_vat_registration_number(frm) {
		custom_erpnext.customer.sync_vat_fields(frm);
	},

	refresh(frm) {
		custom_erpnext.customer.sync_vat_fields(frm, true);
	},
});

frappe.provide("custom_erpnext.customer");

custom_erpnext.customer.sync_vat_fields = function (frm, silent = false) {
	if (!frm.fields_dict.custom_vat_registration_number) return;

	const tax_id = (frm.doc.tax_id || "").trim();
	const vat = (frm.doc.custom_vat_registration_number || "").trim();

	if (tax_id && !vat) {
		frm.set_value("custom_vat_registration_number", tax_id);
	} else if (vat && !tax_id && !silent) {
		frm.set_value("tax_id", vat);
	}
};
