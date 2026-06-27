// Copyright (c) 2026, mohammed-du and contributors

frappe.ui.form.on("Sales Invoice", {
	onload(frm) {
		custom_erpnext.sales_invoice.setup_desk_form(frm);
	},

	refresh(frm) {
		custom_erpnext.sales_invoice.setup_desk_form(frm);
		custom_erpnext.sales_invoice.apply_field_properties(frm);

		if (frm.is_new() && !frm.doc.is_pos && !frm.doc.offline_invoice_id) {
			frm.set_value("is_pos", 0);
			frm.set_value("update_stock", 1);
			frm.set_value("disable_rounded_total", 1);
		}

		if (frm.is_new() && frm.doc.branch) {
			custom_erpnext.sales_invoice.apply_branch_defaults(frm);
		}

		custom_erpnext.sales_invoice.apply_retail_layout(frm);
		custom_erpnext.sales_invoice.configure_items_grid(frm);
		custom_erpnext.sales_invoice.render_invoice_number(frm);
		custom_erpnext.sales_invoice.sync_customer_display_fields(frm);
		custom_erpnext.sales_invoice.render_invoice_status(frm);
		custom_erpnext.sales_invoice.render_quick_summary(frm);
		custom_erpnext.sales_invoice.render_financial_summary(frm);
		custom_erpnext.sales_invoice.render_einvoice_panel(frm);
		custom_erpnext.sales_invoice.render_status_badge(frm);
		custom_erpnext.sales_invoice.load_discount_limits(frm);
		custom_erpnext.sales_invoice.load_zatca_status(frm);
		custom_erpnext.sales_invoice._finalize_panel_sections(frm);
		custom_erpnext.sales_invoice.check_customer_address(frm);
	},

	branch(frm) {
		custom_erpnext.sales_invoice.apply_branch_defaults(frm);
	},

	is_return(frm) {
		custom_erpnext.sales_invoice.apply_branch_naming_series(frm);
	},

	customer(frm) {
		custom_erpnext.sales_invoice.apply_customer_rules(frm);
		custom_erpnext.sales_invoice.sync_customer_display_fields(frm);
		custom_erpnext.sales_invoice.render_quick_summary(frm);
	},

	customer_address(frm) {
		custom_erpnext.sales_invoice.toggle_address_requirement(frm);
		custom_erpnext.sales_invoice.check_customer_address(frm);
	},

	pos_device(frm) {
		if (!frm.doc.pos_device) return;

		frappe.db.get_value(
			"POS Device",
			frm.doc.pos_device,
			["branch", "warehouse", "pos_profile"],
			(r) => {
				if (r.branch) frm.set_value("branch", r.branch);
				if (r.warehouse) frm.set_value("set_warehouse", r.warehouse);
				if (r.pos_profile) frm.set_value("pos_profile", r.pos_profile);
			}
		);
	},

	cashier(frm) {
		custom_erpnext.sales_invoice.load_discount_limits(frm);
	},

	additional_discount_percentage(frm) {
		custom_erpnext.sales_invoice.validate_discount_limit(frm);
	},

	items_add(frm) {
		custom_erpnext.sales_invoice.calculate_item_discounts(frm);
		custom_erpnext.sales_invoice.render_financial_summary(frm);
	},

	validate: async function (frm) {
		custom_erpnext.sales_invoice.calculate_item_discounts(frm);
		custom_erpnext.sales_invoice.validate_discount_limit(frm);
		await custom_erpnext.sales_invoice.validate_b2b_address(frm);
	},

	// Recalculate summary when totals change
	total(frm) {
		custom_erpnext.sales_invoice.render_financial_summary(frm);
		custom_erpnext.sales_invoice.render_quick_summary(frm);
	},
	net_total(frm) {
		custom_erpnext.sales_invoice.render_financial_summary(frm);
	},
	grand_total(frm) {
		custom_erpnext.sales_invoice.render_financial_summary(frm);
		custom_erpnext.sales_invoice.render_quick_summary(frm);
	},
	outstanding_amount(frm) {
		custom_erpnext.sales_invoice.render_financial_summary(frm);
	},
	discount_amount(frm) {
		custom_erpnext.sales_invoice.render_financial_summary(frm);
	},
	total_taxes_and_charges(frm) {
		custom_erpnext.sales_invoice.render_financial_summary(frm);
	},
	paid_amount(frm) {
		custom_erpnext.sales_invoice.render_financial_summary(frm);
	},
});

frappe.ui.form.on("Sales Invoice Item", {
	discount_percentage(frm) {
		custom_erpnext.sales_invoice.calculate_item_discounts(frm);
		custom_erpnext.sales_invoice.render_financial_summary(frm);
	},

	discount_amount(frm) {
		custom_erpnext.sales_invoice.calculate_item_discounts(frm);
		custom_erpnext.sales_invoice.render_financial_summary(frm);
	},

	qty(frm) {
		custom_erpnext.sales_invoice.calculate_item_discounts(frm);
		custom_erpnext.sales_invoice.render_financial_summary(frm);
	},

	rate(frm) {
		custom_erpnext.sales_invoice.calculate_item_discounts(frm);
		custom_erpnext.sales_invoice.render_financial_summary(frm);
	},

	items_remove(frm) {
		custom_erpnext.sales_invoice.render_financial_summary(frm);
	},
});

frappe.provide("custom_erpnext.sales_invoice");

custom_erpnext.sales_invoice.HEADER_CARDS = {
	invoice: {
		title: __("Invoice Data"),
		icon: "receipt",
		fields: [
			"company",
			"branch",
			"naming_series",
			"retail_invoice_number",
			"posting_date",
			"due_date",
			"currency",
			"retail_invoice_status_display",
		],
	},
	customer: {
		title: __("Customer Data"),
		icon: "customer",
		fields: [
			"customer",
			"retail_customer_number",
			"tax_id",
			"address_display",
			"payment_method",
			"payment_terms_template",
		],
	},
	other: {
		title: __("Other Information"),
		icon: "settings",
		fields: [
			"set_warehouse",
			"cost_center",
			"sales_representative",
			"remarks",
			"pos_device",
			"cashier",
			"shift_id",
			"offline_invoice_id",
			"sync_status",
		],
	},
};

custom_erpnext.sales_invoice.VISIBLE_DESK_FIELDS = [
	"company",
	"branch",
	"naming_series",
	"retail_invoice_number",
	"posting_date",
	"due_date",
	"currency",
	"retail_invoice_status_display",
	"customer",
	"retail_customer_number",
	"tax_id",
	"address_display",
	"payment_method",
	"payment_terms_template",
	"set_warehouse",
	"cost_center",
	"sales_representative",
	"remarks",
	"items",
	"taxes_and_charges",
	"taxes",
	"retail_summary_section",
	"retail_financial_summary",
	"retail_einvoice_section",
	"retail_einvoice_badge",
	"e_invoice_type",
	"zatca_status",
	"retail_footer_section",
	"internal_notes",
	"is_e_invoice",
	"payments",
];

custom_erpnext.sales_invoice.HIDDEN_POS_FIELDS = [
	"retail_pos_section",
	"retail_sync_column",
	"section_break_84",
	"section_break_88",
	"base_paid_amount",
	"column_break_86",
	"base_change_amount",
	"column_break_90",
	"change_amount",
	"account_for_change_amount",
	"write_off_outstanding_amount_automatically",
	"sync_log",
	"is_pos_transaction",
];

custom_erpnext.sales_invoice.HIDDEN_DELIVERY_FIELDS = [
	"retail_delivery_section",
	"shipping_cost",
	"delivery_date",
	"driver",
	"delivery_status",
];

custom_erpnext.sales_invoice.ITEM_GRID_FIELDS = [
	"item_code",
	"description",
	"warehouse",
	"qty",
	"rate",
	"discount_percentage",
	"discount_amount",
	"amount",
];

custom_erpnext.sales_invoice.HIDDEN_DESK_FIELDS = [
	"company_tax_id",
	"posting_time",
	"set_posting_time",
	"conversion_rate",
	"selling_price_list",
	"price_list_currency",
	"plc_conversion_rate",
	"ignore_pricing_rule",
	"scan_barcode",
	"last_scanned_warehouse",
	"set_target_warehouse",
	"update_stock",
	"column_break1",
	"column_break_14",
	"column_break_39",
	"section_break_qllv",
	"title",
	"accounting_dimensions_section",
	"dimension_col_break",
	"project",
	"column_break2",
	"total_qty",
	"total_net_weight",
	"column_break_32",
	"base_total",
	"base_net_total",
	"column_break_52",
	"total",
	"net_total",
	"tax_category",
	"incoterm",
	"named_place",
	"column_break_55",
	"column_break_38",
	"base_total_taxes_and_charges",
	"column_break_47",
	"sec_tax_breakup",
	"other_charges_calculation",
	"item_wise_tax_details",
	"is_pos",
	"pos_profile",
	"is_created_using_pos",
	"pos_closing_entry",
	"customer_name",
	"sales_partner",
];

custom_erpnext.sales_invoice.setup_desk_form = function (frm) {
	frm.page.wrapper.toggleClass("sales-invoice-retail-form", true);
	frm.page.wrapper.toggleClass("retail-desk-mode", true);
	frm.page.wrapper.toggleClass("retail-summary-active", true);
};

custom_erpnext.sales_invoice.apply_field_properties = function (frm) {
	frm.set_df_property("naming_series", "read_only", 1);
	frm.set_df_property("update_stock", "read_only", 1);
	frm.set_df_property("is_e_invoice", "read_only", 1);
	frm.set_df_property("e_invoice_type", "read_only", 1);

	const can_override_warehouse = frappe.user.has_role("System Manager");
	frm.set_df_property("set_warehouse", "read_only", !can_override_warehouse);
};

custom_erpnext.sales_invoice.apply_retail_layout = function (frm) {
	const $wrapper = frm.page.wrapper;
	custom_erpnext.sales_invoice._ensure_quick_summary($wrapper);
	custom_erpnext.sales_invoice._ensure_header_grid($wrapper);
	custom_erpnext.sales_invoice._move_fields_to_cards(frm);
	custom_erpnext.sales_invoice._ensure_main_content(frm);
	custom_erpnext.sales_invoice._ensure_bottom_grid(frm);
	custom_erpnext.sales_invoice._ensure_footer_section(frm);
	custom_erpnext.sales_invoice._show_desk_fields(frm);
	custom_erpnext.sales_invoice._hide_desk_clutter(frm);
	custom_erpnext.sales_invoice._hide_pos_clutter(frm);
	custom_erpnext.sales_invoice._hide_delivery_fields(frm);
};

custom_erpnext.sales_invoice._ensure_footer_section = function (frm) {
	const $wrapper = frm.page.wrapper;
	const $main = $wrapper.find(".retail-si-main-content");
	if (!$main.length) return;

	let $footer = $main.find(".retail-si-footer");
	if (!$footer.length) {
		$footer = $('<div class="retail-si-footer"></div>');
		$main.append($footer);
	}

	["retail_footer_section", "internal_notes"].forEach((fn) => {
		custom_erpnext.sales_invoice._move_section_field(frm, fn, $footer);
	});

	const $attach = $wrapper.find(".form-attachments").first();
	if ($attach.length && !$attach.closest(".retail-si-footer").length) {
		$footer.append(
			`<div class="retail-si-attachments-head">${frappe.utils.icon("paperclip", "sm")}<span>${__("Attach Files")}</span></div>`
		);
		$attach.appendTo($footer);
	}
};

custom_erpnext.sales_invoice._show_desk_fields = function (frm) {
	custom_erpnext.sales_invoice.VISIBLE_DESK_FIELDS.forEach((fn) => {
		if (frm.fields_dict[fn]) {
			frm.toggle_display(fn, true);
		}
	});
};

custom_erpnext.sales_invoice.configure_items_grid = function (frm) {
	const grid_field = frm.fields_dict.items;
	if (!grid_field || !grid_field.grid) return;

	const grid = grid_field.grid;
	const child_doctype = grid_field.df.options;

	custom_erpnext.sales_invoice.ITEM_GRID_FIELDS.forEach((fieldname) => {
		const df = frappe.meta.get_docfield(child_doctype, fieldname);
		if (df) {
			df.in_list_view = 1;
		}

		const grid_df = grid.docfields?.find((d) => d.fieldname === fieldname);
		if (grid_df) {
			grid_df.in_list_view = 1;
		}
	});

	if (grid.grid_rows?.length) {
		custom_erpnext.sales_invoice.ITEM_GRID_FIELDS.forEach((fieldname) => {
			if (grid.docfields?.find((d) => d.fieldname === fieldname)) {
				grid.update_docfield_property(fieldname, "in_list_view", 1);
			}
		});
	}

	grid.setup_visible_columns();
	grid.refresh();
};

custom_erpnext.sales_invoice.render_invoice_number = function (frm) {
	const field = frm.fields_dict.retail_invoice_number;
	if (!field || !field.$wrapper) return;

	const number = frm.doc.name || __("New");
	field.$wrapper.find(".retail-invoice-number-display").html(
		`<div class="retail-readonly-value">${frappe.utils.escape_html(number)}</div>`
	);
};

custom_erpnext.sales_invoice.sync_customer_display_fields = function (frm) {
	if (frm.doc.customer) {
		frm.set_value("retail_customer_number", frm.doc.customer);
	} else {
		frm.set_value("retail_customer_number", "");
	}
};

custom_erpnext.sales_invoice._ensure_main_content = function (frm) {
	const $wrapper = frm.page.wrapper;
	const $header = $wrapper.find(".retail-si-header-grid");
	if (!$header.length) return;

	let $main = $wrapper.find(".retail-si-main-content");
	if (!$main.length) {
		$main = $('<div class="retail-si-main-content retail-si-main-panel"></div>');
		$header.after($main);
	}

	const main_fields = ["items_section", "section_break_42", "items"];
	if (frm.doc.is_pos) {
		main_fields.push("payments_section", "payments");
	}

	main_fields.forEach((fn) => {
		custom_erpnext.sales_invoice._move_section_field(frm, fn, $main);
	});
};

custom_erpnext.sales_invoice._ensure_quick_summary = function ($wrapper) {
	if ($wrapper.find(".retail-si-quick-bar").length) return;

	const $bar = $(`<div class="retail-si-quick-bar" role="region" aria-label="${__("Invoice overview")}"></div>`);
	const $tabs = $wrapper.find(".form-tabs-list");
	if ($tabs.length) {
		$bar.insertAfter($tabs);
	} else {
		$wrapper.find(".form-layout").first().prepend($bar);
	}
};

custom_erpnext.sales_invoice._ensure_header_grid = function ($wrapper) {
	if ($wrapper.find(".retail-si-header-grid").length) return;

	const cards = custom_erpnext.sales_invoice.HEADER_CARDS;
	const html = Object.entries(cards)
		.map(([key, cfg]) => {
			const icon = cfg.icon
				? `<span class="retail-si-card__icon">${frappe.utils.icon(cfg.icon, "sm")}</span>`
				: "";
			return `
		<div class="retail-si-card" data-card="${key}">
			<div class="retail-si-card__title">${icon}<span>${cfg.title}</span></div>
			<div class="retail-si-card__body"></div>
		</div>`;
		})
		.join("");

	const $grid = $(`<div class="retail-si-header-grid">${html}</div>`);
	const $quickBar = $wrapper.find(".retail-si-quick-bar");
	const $tabs = $wrapper.find(".form-tabs-list");
	if ($quickBar.length) {
		$grid.insertAfter($quickBar);
	} else if ($tabs.length) {
		$grid.insertAfter($tabs);
	} else {
		$wrapper.find(".form-layout").first().prepend($grid);
	}
};

custom_erpnext.sales_invoice._move_field_wrapper = function (frm, fieldname, $target) {
	const field = frm.fields_dict[fieldname];
	if (!field || !field.$wrapper) return;

	const $el = field.$wrapper.closest(".form-group").length
		? field.$wrapper.closest(".form-group")
		: field.$wrapper;

	if ($el.closest($target).length) return;

	$el.addClass("retail-si-field-moved");
	$el.appendTo($target);
};

custom_erpnext.sales_invoice._move_fields_to_cards = function (frm) {
	const $wrapper = frm.page.wrapper;

	Object.entries(custom_erpnext.sales_invoice.HEADER_CARDS).forEach(([key, cfg]) => {
		const $body = $wrapper.find(`.retail-si-card[data-card="${key}"] .retail-si-card__body`);
		if (!$body.length) return;
		cfg.fields.forEach((fn) => custom_erpnext.sales_invoice._move_field_wrapper(frm, fn, $body));
	});
};

custom_erpnext.sales_invoice._ensure_bottom_grid = function (frm) {
	const $wrapper = frm.page.wrapper;
	const $layout = $wrapper.find(".form-layout").first();

	if (!$layout.find(".retail-si-bottom-grid").length) {
		const $grid = $('<div class="retail-si-bottom-grid"></div>');
		const $summaryCol = $('<div class="form-column retail-si-summary-col"></div>');
		const $taxesCol = $('<div class="form-column retail-si-taxes-col"></div>');
		$grid.append($summaryCol).append($taxesCol);

		const $main = $wrapper.find(".retail-si-main-content");
		if ($main.length) {
			$main.append($grid);
		} else {
			$layout.append($grid);
		}

		frm._retail_summary_col = $summaryCol;
		frm._retail_taxes_col = $taxesCol;
	}

	const $summaryCol = frm._retail_summary_col || $wrapper.find(".retail-si-summary-col");
	const $taxesCol = frm._retail_taxes_col || $wrapper.find(".retail-si-taxes-col");

	[
		"retail_summary_section",
		"retail_financial_summary",
	].forEach((fn) => custom_erpnext.sales_invoice._move_section_field(frm, fn, $summaryCol));

	["taxes_section", "taxes_and_charges", "taxes"].forEach((fn) =>
		custom_erpnext.sales_invoice._move_section_field(frm, fn, $taxesCol)
	);

	custom_erpnext.sales_invoice._ensure_einvoice_column(frm);
	custom_erpnext.sales_invoice._ensure_panel_hosts(frm);
};

custom_erpnext.sales_invoice._ensure_einvoice_column = function (frm) {
	let $einvoiceCol = frm.page.wrapper.find(".retail-si-einvoice-col");
	if (!$einvoiceCol.length) {
		$einvoiceCol = $('<div class="form-column retail-si-einvoice-col"></div>');
		const $grid = frm.page.wrapper.find(".retail-si-bottom-grid");
		if ($grid.length) {
			$grid.append($einvoiceCol);
			$grid.css(
				"grid-template-columns",
				"minmax(260px, 1fr) minmax(280px, 1.2fr) minmax(260px, 1fr)"
			);
		}
	}

	[
		"retail_einvoice_section",
		"is_e_invoice",
		"e_invoice_type",
		"retail_einvoice_badge",
		"pi_number",
		"zatca_status",
		"zatca_reference",
		"zatca_sync_status",
	].forEach((fn) => custom_erpnext.sales_invoice._move_section_field(frm, fn, $einvoiceCol));
};

custom_erpnext.sales_invoice._ensure_panel_hosts = function (frm) {
	const ensure_host = ($col, panel_key, host_class, title) => {
		if (!$col || !$col.length) return $();
		let $panel = $col.find(`.retail-si-panel[data-panel="${panel_key}"]`);
		if (!$panel.length) {
			$panel = $(`
				<div class="retail-si-panel" data-panel="${panel_key}">
					<div class="retail-si-panel__title">${title}</div>
					<div class="${host_class}"></div>
				</div>
			`);
			$col.prepend($panel);
		}
		return $panel.find(`.${host_class}`);
	};

	const $wrapper = frm.page.wrapper;
	frm._retail_summary_host = ensure_host(
		$wrapper.find(".retail-si-summary-col"),
		"summary",
		"retail-si-summary-host",
		__("Amount Summary")
	);
	frm._retail_einvoice_host = ensure_host(
		$wrapper.find(".retail-si-einvoice-col"),
		"einvoice",
		"retail-si-einvoice-host",
		__("E-Invoicing")
	);
};

custom_erpnext.sales_invoice._move_section_field = function (frm, fieldname, $targetCol) {
	const field = frm.fields_dict[fieldname];
	if (!field || !field.$wrapper) return;

	const $section = field.$wrapper.closest(".form-section");
	if (!$section.length) {
		custom_erpnext.sales_invoice._move_field_wrapper(frm, fieldname, $targetCol);
		return;
	}

	if ($section.closest($targetCol).length) return;

	if (!$section.data("retail-original-parent")) {
		$section.data("retail-original-parent", $section.parent());
	}

	$section.appendTo($targetCol);
};

custom_erpnext.sales_invoice._hide_desk_clutter = function (frm) {
	custom_erpnext.sales_invoice.HIDDEN_DESK_FIELDS.forEach((fn) => {
		if (frm.fields_dict[fn]) {
			frm.toggle_display(fn, false);
		}
	});
};

custom_erpnext.sales_invoice._hide_pos_clutter = function (frm) {
	custom_erpnext.sales_invoice.HIDDEN_POS_FIELDS.forEach((fn) => {
		if (frm.fields_dict[fn]) {
			frm.toggle_display(fn, false);
		}
	});
};

custom_erpnext.sales_invoice._hide_delivery_fields = function (frm) {
	custom_erpnext.sales_invoice.HIDDEN_DELIVERY_FIELDS.forEach((fn) => {
		if (frm.fields_dict[fn]) {
			frm.toggle_display(fn, false);
		}
	});
};

custom_erpnext.sales_invoice._get_panel_target = function (frm, host_key, fieldname, panel_class) {
	const host_map = {
		summary: frm._retail_summary_host,
		einvoice: frm._retail_einvoice_host,
	};
	const $host = host_map[host_key];
	if ($host && $host.length) {
		return $host;
	}
	return custom_erpnext.sales_invoice._get_html_panel(frm, fieldname, panel_class);
};

custom_erpnext.sales_invoice._get_html_panel = function (frm, fieldname, panel_class) {
	const field = frm.fields_dict[fieldname];
	if (!field || !field.$wrapper) return $();

	let $panel = field.$wrapper.find(`.${panel_class}`);
	if (!$panel.length) {
		$panel = $(`<div class="${panel_class}"></div>`);
		const $value = field.$wrapper.find(".control-value, .html-field").first();
		if ($value.length) {
			$value.append($panel);
		} else {
			field.$wrapper.append($panel);
		}
	}
	return $panel;
};

custom_erpnext.sales_invoice._finalize_panel_sections = function (frm) {
	const $wrapper = frm.page.wrapper;

	$wrapper
		.find(
			"[data-fieldname='retail_summary_section'], [data-fieldname='retail_einvoice_section'], [data-fieldname='retail_financial_summary'], [data-fieldname='retail_einvoice_badge']"
		)
		.closest(".form-section")
		.removeClass("retail-si-section-empty")
		.show();

	custom_erpnext.sales_invoice.render_financial_summary(frm);
	custom_erpnext.sales_invoice.render_einvoice_panel(frm);
	custom_erpnext.sales_invoice._cleanup_empty_sections($wrapper);
};

custom_erpnext.sales_invoice._cleanup_empty_sections = function ($wrapper) {
	const protected_markers =
		".retail-si-summary-host, .retail-si-einvoice-host, .retail-financial-summary, .retail-einvoice-badge, [data-fieldname='retail_summary_section'], [data-fieldname='retail_einvoice_section']";

	$wrapper.find(".form-section").each(function () {
		const $section = $(this);
		if ($section.find(protected_markers).length) {
			$section.removeClass("retail-si-section-empty");
			return;
		}
		const hasVisible = $section.find(".frappe-control:visible, .grid-field:visible").length > 0;
		const hasGrid = $section.find(".form-grid:visible").length > 0;
		$section.toggleClass("retail-si-section-empty", !hasVisible && !hasGrid);
	});
};

custom_erpnext.sales_invoice.get_docstatus_indicator = function (docstatus) {
	if (docstatus === 1) return { label: __("Submitted"), color: "blue" };
	if (docstatus === 2) return { label: __("Cancelled"), color: "red" };
	return { label: __("Draft"), color: "orange" };
};

custom_erpnext.sales_invoice.get_zatca_indicator_color = function (status) {
	const map = {
		Pending: "orange",
		Processing: "blue",
		Cleared: "green",
		Reported: "green",
		Rejected: "red",
	};
	return map[status] || "orange";
};

custom_erpnext.sales_invoice.render_invoice_status = function (frm) {
	const { label, color } = custom_erpnext.sales_invoice.get_docstatus_indicator(frm.doc.docstatus);
	const field = frm.fields_dict.retail_invoice_status_display;
	if (field && field.$wrapper) {
		field.$wrapper
			.find(".retail-invoice-status-display")
			.html(`<span class="indicator-pill ${color}">${label}</span>`);
	}
};

custom_erpnext.sales_invoice.render_quick_summary = function (frm) {
	const $bar = frm.page.wrapper.find(".retail-si-quick-bar");
	if (!$bar.length) return;

	const currency = frm.doc.currency || frappe.defaults.get_default("currency");
	const fmt = (val) => format_currency(flt(val), currency);
	const { label: status_label, color: status_color } =
		custom_erpnext.sales_invoice.get_docstatus_indicator(frm.doc.docstatus);
	const invoice_no = frm.doc.name || __("New");
	const customer = frm.doc.customer_name || frm.doc.customer || "—";
	const posting_date = frm.doc.posting_date
		? frappe.datetime.str_to_user(frm.doc.posting_date)
		: "—";

	const items = [
		{ label: __("Invoice"), value: invoice_no },
		{ label: __("Customer"), value: customer },
		{ label: __("Date"), value: posting_date },
		{
			label: __("Total Due"),
			value: fmt(frm.doc.grand_total),
			amount: true,
		},
	];

	let html = items
		.map(
			(item) => `
		<div class="retail-si-quick-bar__item">
			<span class="retail-si-quick-bar__label">${item.label}</span>
			<span class="retail-si-quick-bar__value${item.amount ? " retail-si-quick-bar__value--amount" : ""}">${frappe.utils.escape_html(String(item.value))}</span>
		</div>`
		)
		.join("");

	html += `
		<div class="retail-si-quick-bar__item retail-si-quick-bar__item--status">
			<span class="retail-si-quick-bar__label">${__("Status")}</span>
			<span class="indicator-pill ${status_color}">${status_label}</span>
		</div>`;

	$bar.html(html);
};

custom_erpnext.sales_invoice.render_financial_summary = function (frm) {
	const $panel = custom_erpnext.sales_invoice._get_panel_target(
		frm,
		"summary",
		"retail_financial_summary",
		"retail-financial-summary"
	);
	if (!$panel.length) return;

	const currency = frm.doc.currency || frappe.defaults.get_default("currency");
	const fmt = (val) => format_currency(flt(val), currency);

	const total_before_discount = flt(frm.doc.total);
	const discount = flt(frm.doc.discount_amount);
	const before_tax = flt(frm.doc.net_total);
	const tax = flt(frm.doc.total_taxes_and_charges);
	const grand = flt(frm.doc.grand_total);
	const paid = flt(frm.doc.paid_amount);
	const outstanding = flt(frm.doc.outstanding_amount);

	const html = `
		<table class="retail-summary-table" role="table" aria-label="${__("Amount Summary")}">
			<tbody>
			<tr>
				<td>${__("Total Before Discount")}</td>
				<td>${fmt(total_before_discount)}</td>
			</tr>
			<tr class="retail-summary-discount">
				<td>${__("Total Discount")}</td>
				<td>${fmt(discount)}</td>
			</tr>
			<tr>
				<td>${__("Amount Before Tax")}</td>
				<td>${fmt(before_tax)}</td>
			</tr>
			<tr>
				<td>${__("Total Tax")}</td>
				<td>${fmt(tax)}</td>
			</tr>
			<tr class="retail-summary-grand">
				<td colspan="2">
					<div class="retail-summary-grand-box">
						<div class="retail-summary-grand-label">${__("Total Due")}</div>
						<div class="retail-summary-grand-value">${fmt(grand)}</div>
					</div>
				</td>
			</tr>
			<tr>
				<td>${__("Amount Paid")}</td>
				<td>${fmt(paid)}</td>
			</tr>
			<tr class="retail-summary-outstanding">
				<td>${__("Remaining Amount")}</td>
				<td>${fmt(outstanding)}</td>
			</tr>
			</tbody>
		</table>`;

	$panel.html(html);
};

custom_erpnext.sales_invoice.render_einvoice_panel = function (frm) {
	const $panel = custom_erpnext.sales_invoice._get_panel_target(
		frm,
		"einvoice",
		"retail_einvoice_badge",
		"retail-einvoice-badge"
	);
	if (!$panel.length) return;

	const type_class = frm.doc.e_invoice_type === "B2B" ? "badge-b2b" : "badge-b2c";
	const type_label =
		frm.doc.e_invoice_type === "B2B"
			? __("B2B - Business to Business")
			: __("B2C - Business to Consumer");
	const zatca_status = frm.doc.zatca_status || "Pending";
	const zatca_label = custom_erpnext.sales_invoice.get_zatca_status_label(zatca_status);
	const zatca_color = custom_erpnext.sales_invoice.get_zatca_indicator_color(zatca_status);
	const is_e_invoice = frm.doc.is_e_invoice ? __("Yes") : __("No");
	const pi_number = (frm.doc.pi_number || "").trim();
	const zatca_reference = (frm.doc.zatca_reference || "").trim();
	const sync_status = (frm.doc.zatca_sync_status || "").trim();

	const meta_rows = [
		pi_number
			? `<div class="retail-einvoice-meta__row"><span class="retail-einvoice-meta__label">${__("Tax Invoice Number")}</span><span class="retail-einvoice-meta__value">${frappe.utils.escape_html(pi_number)}</span></div>`
			: "",
		zatca_reference
			? `<div class="retail-einvoice-meta__row"><span class="retail-einvoice-meta__label">${__("ZATCA Reference")}</span><span class="retail-einvoice-meta__value">${frappe.utils.escape_html(zatca_reference)}</span></div>`
			: "",
		sync_status
			? `<div class="retail-einvoice-meta__row"><span class="retail-einvoice-meta__label">${__("ZATCA Sync Status")}</span><span class="retail-einvoice-meta__value">${frappe.utils.escape_html(sync_status)}</span></div>`
			: "",
	]
		.filter(Boolean)
		.join("");

	const html = `
		<div class="retail-einvoice-panel">
			<div class="retail-einvoice-panel__header">
				<div class="retail-einvoice-panel__title">
					${frappe.utils.icon("file-text", "sm")}
					<span>${__("E-Invoice")}</span>
				</div>
				<span class="retail-einvoice-type-badge ${type_class}">${frm.doc.e_invoice_type || "B2C"}</span>
				<span class="like-disabled-input retail-einvoice-type-label">${type_label}</span>
			</div>
			<div class="retail-einvoice-status-row">
				<span class="retail-einvoice-status-label">${__("Enabled")}</span>
				<span class="indicator-pill ${frm.doc.is_e_invoice ? "green" : "gray"}">${is_e_invoice}</span>
			</div>
			<div class="retail-einvoice-status-row">
				<span class="retail-einvoice-status-label">${__("ZATCA Status")}</span>
				<span class="indicator-pill ${zatca_color}">${zatca_label}</span>
			</div>
			${meta_rows ? `<div class="retail-einvoice-meta">${meta_rows}</div>` : ""}
			<div class="retail-einvoice-note">${__(
				"Invoice will be sent to ZATCA automatically after submission."
			)}</div>
		</div>`;

	$panel.html(html);
};

custom_erpnext.sales_invoice.get_zatca_status_label = function (status) {
	const map = {
		Pending: __("Not Sent"),
		Processing: __("Processing"),
		Cleared: __("Cleared"),
		Reported: __("Reported"),
		Rejected: __("Rejected"),
	};
	return map[status] || status || __("Not Sent");
};

custom_erpnext.sales_invoice.apply_branch_defaults = function (frm) {
	custom_erpnext.sales_invoice.apply_branch_naming_series(frm);

	if (!frm.doc.branch) return;

	frappe.db.get_value(
		"Company Branch",
		frm.doc.branch,
		["warehouse", "cost_center"],
		(r) => {
			if (r.warehouse) {
				frm.set_value("set_warehouse", r.warehouse);
			}
			if (r.cost_center && !frm.doc.cost_center) {
				frm.set_value("cost_center", r.cost_center);
			}
		}
	);
};

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

custom_erpnext.sales_invoice.apply_customer_rules = function (frm) {
	if (!frm.doc.customer) {
		frm.set_value("e_invoice_type", "B2C");
		custom_erpnext.sales_invoice.render_einvoice_panel(frm);
		custom_erpnext.sales_invoice.toggle_address_requirement(frm);
		return;
	}

	frappe.call({
		method: "custom_erpnext.api.client.get_customer_einvoice_type",
		args: { customer: frm.doc.customer },
		callback(r) {
			const payload = r.message || {};
			const tax_id = (payload.tax_id || "").trim();

			if (tax_id) {
				frm.set_value("tax_id", tax_id);
			}

			frm.set_value("is_e_invoice", 1);
			frm.set_value("e_invoice_type", payload.e_invoice_type || "B2C");
			frm._is_b2b_customer = !!payload.is_b2b;
			custom_erpnext.sales_invoice.render_einvoice_panel(frm);
			custom_erpnext.sales_invoice.toggle_address_requirement(frm);
			custom_erpnext.sales_invoice.check_customer_address(frm);
		},
	});

	if (!frm.doc.customer_address) {
		frappe.call({
			method: "frappe.contacts.doctype.address.address.get_default_address",
			args: { doctype: "Customer", name: frm.doc.customer },
			callback(r) {
				if (r.message) {
					frm.set_value("customer_address", r.message);
					custom_erpnext.sales_invoice.check_customer_address(frm);
				}
			},
		});
	}
};

custom_erpnext.sales_invoice.is_b2b = function (frm) {
	if (typeof frm._is_b2b_customer === "boolean") {
		return frm._is_b2b_customer;
	}
	const tax_id = (frm.doc.tax_id || "").trim();
	return tax_id.length === 15 && /^\d+$/.test(tax_id);
};

custom_erpnext.sales_invoice.toggle_address_requirement = function (frm) {
	frm.toggle_reqd("customer_address", custom_erpnext.sales_invoice.is_b2b(frm));
};

custom_erpnext.sales_invoice.load_zatca_status = function (frm) {
	if (frm.is_new() || !frm.doc.name) return;

	frappe.call({
		method: "custom_erpnext.api.client.get_sales_invoice_zatca_status",
		args: { sales_invoice: frm.doc.name },
		callback(r) {
			const payload = r.message || {};
			if (payload.zatca_status) {
				frm.set_value("zatca_status", payload.zatca_status);
			}
			if (payload.zatca_reference) {
				frm.set_value("zatca_reference", payload.zatca_reference);
			}
			if (payload.zatca_sync_status) {
				frm.set_value("zatca_sync_status", payload.zatca_sync_status);
			}
			if (payload.e_invoice_type) {
				frm.set_value("e_invoice_type", payload.e_invoice_type);
			}
			custom_erpnext.sales_invoice.render_einvoice_panel(frm);
		},
	});
};

custom_erpnext.sales_invoice.validate_b2b_address = function (frm) {
	if (!custom_erpnext.sales_invoice.is_b2b(frm)) {
		return Promise.resolve();
	}

	if (!frm.doc.customer_address) {
		frappe.throw(__("Customer Address is mandatory for B2B customers with Tax Number"));
	}

	return frappe
		.call({
			method: "custom_erpnext.api.client.validate_zatca_customer_address",
			args: { customer_address: frm.doc.customer_address },
		})
		.then((r) => {
			const payload = r.message || {};
			if (!payload.valid) {
				const issues = (payload.issues || []).join("<hr>");
				const edit_link = payload.edit_url || "";
				frappe.throw({
					title: __("Invalid Address Error"),
					message: edit_link ? `${issues}<hr>${edit_link}` : issues,
				});
			}
		});
};

custom_erpnext.sales_invoice.check_customer_address = function (frm) {
	if (!frm.doc.customer || !custom_erpnext.sales_invoice.is_b2b(frm)) {
		custom_erpnext.sales_invoice.render_address_warning(frm, { valid: true });
		return;
	}

	if (frm.doc.customer_address) {
		frm.add_custom_button(
			__("Edit Address"),
			() => frappe.set_route("Form", "Address", frm.doc.customer_address),
			__("Customer")
		);
	}

	if (!frm.doc.customer_address) {
		custom_erpnext.sales_invoice.render_address_warning(frm, {
			valid: false,
			issues: [__("Customer Address is mandatory for B2B customers with Tax Number")],
		});
		return;
	}

	frappe.call({
		method: "custom_erpnext.api.client.validate_zatca_customer_address",
		args: { customer_address: frm.doc.customer_address },
		callback(r) {
			custom_erpnext.sales_invoice.render_address_warning(frm, r.message || {});
		},
	});
};

custom_erpnext.sales_invoice.render_address_warning = function (frm, payload) {
	const $card = frm.page.wrapper.find('.retail-si-card[data-card="customer"] .retail-si-card__body');
	$card.find(".retail-address-alert").remove();

	if (!payload || payload.valid) return;

	const issues = (payload.issues || []).map((msg) => frappe.utils.escape_html(msg)).join("<br>");
	const edit_btn = payload.address
		? `<button type="button" class="btn btn-xs btn-default retail-address-alert__edit">${__(
				"Update Address"
		  )}</button>`
		: "";

	const html = `
		<div class="retail-address-alert" role="alert">
			<div class="retail-address-alert__title">${__("Invalid Address Error")}</div>
			<div class="retail-address-alert__body">${issues}</div>
			${edit_btn}
		</div>`;

	const $alert = $(html);
	if (payload.address) {
		$alert.find(".retail-address-alert__edit").on("click", () => {
			frappe.set_route("Form", "Address", payload.address);
		});
	}
	$card.prepend($alert);
};

custom_erpnext.sales_invoice.render_status_badge = function (frm) {
	const { label, color } = custom_erpnext.sales_invoice.get_docstatus_indicator(frm.doc.docstatus);

	if (!frm.page.$status_badge || !frm.page.$status_badge.length) {
		frm.page.$status_badge = $(
			`<span class="retail-si-status-badge indicator-pill ${color}">${label}</span>`
		);
		frm.page.title_area.append(frm.page.$status_badge);
	} else {
		frm.page.$status_badge
			.removeClass("orange blue red green draft submitted cancelled")
			.addClass(color)
			.text(label);
	}
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
		frappe.throw(
			__("Discount {0}% exceeds allowed limit {1}% for user {2}.", [
				discount_pct,
				max_discount,
				cashier,
			])
		);
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
