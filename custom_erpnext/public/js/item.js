// Copyright (c) 2026, mohammed-du and contributors

frappe.ui.form.on("Item", {
	standard_rate(frm) {
		custom_erpnext.item.validate_selling_prices(frm);
	},

	min_selling_price(frm) {
		custom_erpnext.item.validate_selling_prices(frm);
	},

	max_selling_price(frm) {
		custom_erpnext.item.validate_selling_prices(frm);
	},

	validate(frm) {
		return custom_erpnext.item.validate_selling_prices(frm);
	},
});

frappe.provide("custom_erpnext.item");

custom_erpnext.item.validate_selling_prices = function (frm) {
	const rate = flt(frm.doc.standard_rate);
	const min_price = flt(frm.doc.min_selling_price);
	const max_price = flt(frm.doc.max_selling_price);

	if (min_price && max_price && min_price > max_price) {
		frappe.throw(__("Min Selling Price cannot be greater than Max Selling Price"));
	}

	if (rate && min_price && rate < min_price) {
		frappe.throw(__("Standard Rate {0} cannot be less than Min Selling Price {1}", [rate, min_price]));
	}

	if (rate && max_price && rate > max_price) {
		frappe.throw(__("Standard Rate {0} cannot exceed Max Selling Price {1}", [rate, max_price]));
	}
};
