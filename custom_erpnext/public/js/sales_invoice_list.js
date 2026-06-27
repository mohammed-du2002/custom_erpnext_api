// Copyright (c) 2026, mohammed-du and contributors

frappe.listview_settings["Sales Invoice"] = {
	onload(listview) {
		const route_options = frappe.route_options || {};
		const is_pos_route = route_options.is_pos !== undefined && route_options.is_pos !== null;

		if (!is_pos_route) {
			listview.filter_area.add([[listview.doctype, "is_pos", "=", 0]]);
		}

		listview.page.add_menu_item(__("POS Invoices"), () => {
			frappe.route_options = { is_pos: 1 };
			frappe.set_route("List", "Sales Invoice");
		});

		listview.page.add_menu_item(__("Sales Invoices"), () => {
			frappe.route_options = { is_pos: 0 };
			frappe.set_route("List", "Sales Invoice");
		});
	},
};
