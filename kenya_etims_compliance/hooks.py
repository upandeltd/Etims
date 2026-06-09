import frappe

app_name = "kenya_etims_compliance"
app_title = "Kenya Etims Compliance"
app_publisher = "Upande Ltd"
app_description = "Frappe Etims Compliance App"
app_email = "dev@upande.com"
app_license = "mit"
required_apps = ["frappe", "erpnext"]

setup_wizard_requires_login = 0
setup_wizard_not_required = 1

# App screen tile (v16 desk home)
add_to_apps_screen = [
	{
		"name": "kenya_etims_compliance",
		"logo": "/assets/kenya_etims_compliance/images/etims-logo.svg",
		"title": "eTIMS Compliance",
		"route": "/app/etims-compliance",
		"has_permission": "kenya_etims_compliance.check_app_permission",
	}
]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/kenya_etims_compliance/css/kenya_etims_compliance.css"
app_include_js = "/assets/kenya_etims_compliance/js/etims_icons.js"

# include js, css files in header of web template
# web_include_css = "/assets/kenya_etims_compliance/css/kenya_etims_compliance.css"
# web_include_js = "/assets/kenya_etims_compliance/js/kenya_etims_compliance.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "kenya_etims_compliance/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
doctype_js = {
	# "doctype" : "public/js/doctype.js"
	"Item": "custom_methods/item.js",
	"Customer": "custom_methods/customer.js",
	"BOM": "custom_methods/bom.js",
	"Sales Invoice": "custom_methods/sales_invoice.js",
	"Purchase Invoice": "custom_methods/purchase_invoice.js",
	"Supplier": "custom_methods/supplier.js",
}

# include js in doctype views
doctype_list_js = {
	"Item": "custom_methods/item_list.js",
}

# Svg Icons
# ------------------
# include app icons in desk (loaded via app_include_js instead for compatibility)
# app_include_icons = "kenya_etims_compliance/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# "Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# escpos_qr: emits a byte-safe ESC/POS QR command for the thermal POS receipt
# print format (falls back to "" when not byte-safe — see utils/escpos.py).
jinja = {
	"methods": ["kenya_etims_compliance.utils.escpos.escpos_qr"],
}

# Installation
# ------------

before_install = "kenya_etims_compliance.installation.etims_roles.before_install"
after_install = "kenya_etims_compliance.installation.after_install.after_install"
after_migrate = [
	"kenya_etims_compliance.installation.after_install.setup_workspace_sidebar",
	"kenya_etims_compliance.custom_methods.install_queue_fields.install_queue_fields",
	# Create the Number Cards / Dashboard Charts the eTIMS workspace references
	"kenya_etims_compliance.setup_dashboard.execute",
]

# Uninstallation
# ------------

# before_uninstall = "kenya_etims_compliance.uninstall.before_uninstall"
# after_uninstall = "kenya_etims_compliance.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "kenya_etims_compliance.utils.before_app_install"
# after_app_install = "kenya_etims_compliance.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "kenya_etims_compliance.utils.before_app_uninstall"
# after_app_uninstall = "kenya_etims_compliance.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "kenya_etims_compliance.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# "Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# "Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# "ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Sales Invoice": {
		"before_save": "kenya_etims_compliance.custom_methods.sales_invoice.validate",
		"before_submit": "kenya_etims_compliance.custom_methods.sales_invoice.trnsSalesSaveWrReq",
		"on_update": "kenya_etims_compliance.custom_methods.sales_invoice.insert_invoice_number",
		"on_submit": [
			"kenya_etims_compliance.custom_methods.bin.on_submit",
			"kenya_etims_compliance.custom_methods.sales_invoice.show_etims_queued_message",
		],
	},
	"Stock Entry": {
		"before_submit": "kenya_etims_compliance.custom_methods.stock.update_stock_to_etims",
		"before_validate": "kenya_etims_compliance.custom_methods.stock.insert_tax_rate_and_amount",
		"on_submit": "kenya_etims_compliance.custom_methods.bin_stock_entry.on_submit",
	},
	"Item": {"before_save": "kenya_etims_compliance.custom_methods.item.autofill_tims_info"},
	"Supplier": {"validate": "kenya_etims_compliance.custom_methods.supplier.validate"},
	"Purchase Invoice": {
		"before_save": "kenya_etims_compliance.custom_methods.purchase_invoice.validate",
		"before_submit": "kenya_etims_compliance.custom_methods.purchase_invoice.trnsPurchaseSaveReq",
		"on_update": "kenya_etims_compliance.custom_methods.purchase_invoice.insert_invoice_number",
		"on_change": "kenya_etims_compliance.custom_methods.purchase_invoice.add_taxes",
		"on_submit": "kenya_etims_compliance.custom_methods.bin.on_submit",
	},
	# Phase 1: Invoice Checker API Integration - Payment Validation
	"Payment Entry": {
		"before_submit": "kenya_etims_compliance.custom_methods.payment_entry.validate_payment_for_etims_invoice"
	},
	# "eTIMS Purchase Invoice": {
	#     "on_update": "kenya_etims_compliance.custom_methods.etims_purchase_invoice.update_stock_to_etims",
	# },
	# "eTIMS Stock Movement": {
	#     "on_update": "kenya_etims_compliance.custom_methods.etims_stock_movement.update_stock_to_etims",
	# }
}
# Scheduled Tasks
# ---------------

scheduler_events = {
	"cron": {
		"*/5 * * * *": ["kenya_etims_compliance.custom_methods.queue_processor.retry_failed_invoices"],
		# Per TIS spec §21.8: pull pending KRA purchase records every 15 min
		"*/15 * * * *": ["kenya_etims_compliance.tasks.fetch_purchase_transactions"],
	},
	"daily": [
		"kenya_etims_compliance.tasks.fetch_kra_notices",
		"kenya_etims_compliance.tasks.run_reconciliation_task",
		"kenya_etims_compliance.tasks.fetch_import_items",
		"kenya_etims_compliance.tasks.send_deadline_reminders",
	],
	"weekly": [
		"kenya_etims_compliance.tasks.verify_supplier_pins",
		"kenya_etims_compliance.tasks.calculate_supplier_scores",
	],
	"monthly": [
		"kenya_etims_compliance.tasks.generate_compliance_score",
	],
}

# Testing
# -------

# before_tests = "kenya_etims_compliance.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# "frappe.desk.doctype.event.event.get_events": "kenya_etims_compliance.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# "Task": "kenya_etims_compliance.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["kenya_etims_compliance.utils.before_request"]
# after_request = ["kenya_etims_compliance.utils.after_request"]

# Job Events
# ----------
# before_job = ["kenya_etims_compliance.utils.before_job"]
# after_job = ["kenya_etims_compliance.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# {
# "doctype": "{doctype_1}",
# "filter_by": "{filter_by}",
# "redact_fields": ["{field_1}", "{field_2}"],
# "partial": 1,
# },
# {
# "doctype": "{doctype_2}",
# "filter_by": "{filter_by}",
# "partial": 1,
# },
# {
# "doctype": "{doctype_3}",
# "strict": False,
# },
# {
# "doctype": "{doctype_4}"
# }
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# "kenya_etims_compliance.auth.validate"
# ]

fixtures = [
	{"dt": "Custom Field", "filters": [["module", "=", "Kenya Etims Compliance"]]},
	{"dt": "Workspace", "filters": [["name", "=", "eTIMS Compliance"]]},
	{
		"dt": "Role",
		"filters": [
			[
				"name",
				"in",
				[
					"eTIMS Administrator",
					"eTIMS Manager",
					"eTIMS Operator",
					"eTIMS Auditor",
					"eTIMS Sales Clerk",
					"eTIMS Purchase Clerk",
					"eTIMS Store Keeper",
				],
			]
		],
	},
	{"dt": "eTIMS Credit Note Reason", "filters": [["code", "!=", ""]]},
]

# "Workspace Sidebar" is a v16+ DocType. Including it unconditionally breaks
# `bench export-fixtures` on v15 (the DocType/table does not exist). Add it only
# on v16+, matching the version guard in installation/after_install.py. The
# import path (sync_fixtures) already skips the v16 sidebar JSON on v15.
try:
	if int(frappe.__version__.split(".")[0]) >= 16:
		fixtures.append(
			{"dt": "Workspace Sidebar", "filters": [["module", "=", "Kenya Etims Compliance"]]}
		)
except Exception:
	pass
