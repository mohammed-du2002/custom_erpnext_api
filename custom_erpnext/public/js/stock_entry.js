// Copyright (c) 2026, mohammed-du and contributors

frappe.ui.form.on("Stock Entry", {
	setup(frm) {
		custom_erpnext.stock_entry.load_negative_stock_setting(frm);
	},

	from_warehouse(frm) {
		custom_erpnext.stock_entry.load_negative_stock_setting(frm);
	},

	transfer_request(frm) {
		if (!frm.doc.transfer_request) return;

		frappe.db.get_doc("Stock Transfer Request", frm.doc.transfer_request).then((doc) => {
			if (doc.from_warehouse) frm.set_value("from_warehouse", doc.from_warehouse);
			if (doc.to_warehouse) frm.set_value("to_warehouse", doc.to_warehouse);
			if (doc.transfer_cost) frm.set_value("transfer_cost", doc.transfer_cost);

			if (doc.items && doc.items.length && !frm.doc.items.length) {
				doc.items.forEach((row) => {
					frm.add_child("items", {
						item_code: row.item_code,
						qty: row.qty,
						uom: row.uom,
						s_warehouse: doc.from_warehouse,
						t_warehouse: doc.to_warehouse,
					});
				});
				frm.refresh_field("items");
			}
		});
	},

	validate(frm) {
		custom_erpnext.stock_entry.validate_stock_availability(frm);
	},
});

frappe.ui.form.on("Stock Entry Detail", {
	qty(frm, cdt, cdn) {
		custom_erpnext.stock_entry.validate_row_availability(frm, locals[cdt][cdn]);
	},

	s_warehouse(frm, cdt, cdn) {
		custom_erpnext.stock_entry.validate_row_availability(frm, locals[cdt][cdn]);
	},
});

frappe.provide("custom_erpnext.stock_entry");

custom_erpnext.stock_entry.load_negative_stock_setting = function (frm) {
	const warehouse = frm.doc.from_warehouse;
	if (!warehouse) return;

	frappe.db.get_value("Warehouse", warehouse, "allow_negative_stock", (r) => {
		frm.doc.__allow_negative = r.allow_negative_stock;
	});
};

custom_erpnext.stock_entry.validate_stock_availability = function (frm) {
	(frm.doc.items || []).forEach((row) => {
		custom_erpnext.stock_entry.validate_row_availability(frm, row);
	});
};

custom_erpnext.stock_entry.validate_row_availability = function (frm, row) {
	if (!row.s_warehouse || !row.item_code) return;

	const required_qty = flt(row.qty);
	const available = flt(row.actual_qty);

	if (required_qty > 0 && available < required_qty && !frm.doc.__allow_negative) {
		frappe.throw(
			__("Item {0}: required {1}, available {2} in warehouse {3}", [
				row.item_code,
				required_qty,
				available,
				row.s_warehouse,
			])
		);
	}
};
