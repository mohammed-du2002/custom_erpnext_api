app_name = "custom_erpnext"
app_title = "Custom Erpnext"
app_publisher = "mohammed-du"
app_description = "Custom Update to SuperMarker Project"
app_email = "tsc4it@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "custom_erpnext",
# 		"logo": "/assets/custom_erpnext/logo.png",
# 		"title": "Custom Erpnext",
# 		"route": "/custom_erpnext",
# 		"has_permission": "custom_erpnext.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/custom_erpnext/css/custom_erpnext.css"
# app_include_js = "/assets/custom_erpnext/js/custom_erpnext.js"

# include js, css files in header of web template
# web_include_css = "/assets/custom_erpnext/css/custom_erpnext.css"
# web_include_js = "/assets/custom_erpnext/js/custom_erpnext.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "custom_erpnext/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
	"Sales Invoice": "public/js/sales_invoice.js",
	"Item": "public/js/item.js",
	"POS Profile": "public/js/pos_profile.js",
	"Purchase Invoice": "public/js/purchase_invoice.js",
	"Stock Entry": "public/js/stock_entry.js",
}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "custom_erpnext/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "custom_erpnext.utils.jinja_methods",
# 	"filters": "custom_erpnext.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "custom_erpnext.install.before_install"
# after_install = "custom_erpnext.install.after_install"
after_migrate = [
	"custom_erpnext.setup.workflows.setup_workflows",
	"custom_erpnext.setup.user_permissions.sync_all_user_branch_permissions",
	"custom_erpnext.setup.naming_series.sync_all_branch_naming_series",
]

# Uninstallation
# ------------

# before_uninstall = "custom_erpnext.uninstall.before_uninstall"
# after_uninstall = "custom_erpnext.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "custom_erpnext.utils.before_app_install"
# after_app_install = "custom_erpnext.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "custom_erpnext.utils.before_app_uninstall"
# after_app_uninstall = "custom_erpnext.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "custom_erpnext.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "custom_erpnext.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

from custom_erpnext.services.branch_permission_service import BRANCH_ISOLATED_DOCTYPES
from custom_erpnext.services.naming_series_service import BRANCH_NAMING_DOCTYPES

_NAMING_SERIES_VALIDATE = "custom_erpnext.services.naming_series_service.apply_branch_naming_series"
_BRANCH_VALIDATE = "custom_erpnext.services.branch_permission_service.validate_document_branch"


def _branch_validate_handlers(doctype):
	handlers = [_BRANCH_VALIDATE]
	if doctype in BRANCH_NAMING_DOCTYPES:
		handlers.append(_NAMING_SERIES_VALIDATE)
	return handlers

permission_query_conditions = {
	doctype: "custom_erpnext.services.branch_permission_service.get_permission_query_conditions"
	for doctype in BRANCH_ISOLATED_DOCTYPES
}

has_permission = {
	doctype: "custom_erpnext.services.branch_permission_service.has_branch_permission"
	for doctype in BRANCH_ISOLATED_DOCTYPES
}

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Item": {
		"validate": "custom_erpnext.services.item_service.validate_selling_prices",
		"on_update": "custom_erpnext.services.sync_service.trigger_urgent_sync_for_item",
	},
	"Item Price": {
		"on_update": "custom_erpnext.services.sync_service.trigger_urgent_sync_for_item_price",
	},
	"Material Request": {
		"validate": _branch_validate_handlers("Material Request"),
		"on_update": "custom_erpnext.setup.workflows.on_material_request_update",
	},
	"Stock Transfer Request": {
		"validate": _branch_validate_handlers("Stock Transfer Request"),
		"on_update": "custom_erpnext.setup.workflows.on_stock_transfer_update",
	},
	"User Discount Profile": {
		"on_update": "custom_erpnext.services.branch_permission_service.sync_profile_branch_permissions",
	},
	"User": {
		"on_update": "custom_erpnext.services.branch_permission_service.sync_user_default_branch",
	},
	"Sales Invoice": {
		"validate": _branch_validate_handlers("Sales Invoice"),
	},
	"Purchase Order": {
		"validate": _branch_validate_handlers("Purchase Order"),
	},
	"Purchase Invoice": {
		"validate": _branch_validate_handlers("Purchase Invoice"),
	},
	"Purchase Receipt": {
		"validate": _branch_validate_handlers("Purchase Receipt"),
	},
	"Landed Cost Voucher": {
		"validate": "custom_erpnext.services.branch_permission_service.validate_document_branch",
	},
	"POS Profile": {
		"validate": "custom_erpnext.services.branch_permission_service.validate_document_branch",
	},
	"Warehouse": {
		"validate": "custom_erpnext.services.branch_permission_service.validate_document_branch",
	},
	"Customer": {
		"validate": "custom_erpnext.services.branch_permission_service.validate_document_branch",
	},
	"Supplier": {
		"validate": "custom_erpnext.services.branch_permission_service.validate_document_branch",
	},
	"Daily Sales Summary": {
		"validate": _branch_validate_handlers("Daily Sales Summary"),
	},
	"POS Device": {
		"validate": "custom_erpnext.services.branch_permission_service.validate_document_branch",
	},
	"Payment Method Config": {
		"validate": "custom_erpnext.services.branch_permission_service.validate_document_branch",
	},
	"Party Account Mapping": {
		"validate": "custom_erpnext.services.branch_permission_service.validate_document_branch",
	},
	"User Activity Monitor": {
		"validate": "custom_erpnext.services.branch_permission_service.validate_document_branch",
	},
	"Branch Section": {
		"validate": "custom_erpnext.services.branch_permission_service.validate_document_branch",
	},
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"cron": {
		"*/10 * * * *": ["custom_erpnext.tasks.run_scheduled_sync"],
	},
	"hourly": ["custom_erpnext.tasks.check_item_reorder"],
}

# Testing
# -------

# before_tests = "custom_erpnext.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "custom_erpnext.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "custom_erpnext.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "custom_erpnext.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["custom_erpnext.utils.before_request"]
# after_request = ["custom_erpnext.utils.after_request"]

# Job Events
# ----------
# before_job = ["custom_erpnext.utils.before_job"]
# after_job = ["custom_erpnext.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"custom_erpnext.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

