app_name = "kenya_etims_compliance"
app_title = "Kenya Etims Compliance"
app_publisher = "Upande Ltd"
app_description = "Frappe Etims Compliance App"
app_email = "dev@upande.com"
app_license = "mit"
# required_apps = []

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/kenya_etims_compliance/css/kenya_etims_compliance.css"
# app_include_js = "/assets/kenya_etims_compliance/js/kenya_etims_compliance.js"

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
	"Item" : "custom_methods/item.js",
    "Customer" : "custom_methods/customer.js",
    "BOM" : "custom_methods/bom.js",
    "Sales Invoice": "custom_methods/sales_invoice.js",
    "Purchase Invoice": "custom_methods/purchase_invoice.js"
}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "kenya_etims_compliance/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
#	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
#	"methods": "kenya_etims_compliance.utils.jinja_methods",
#	"filters": "kenya_etims_compliance.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "kenya_etims_compliance.install.before_install"
# after_install = "kenya_etims_compliance.install.after_install"

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
#	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
#	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
#	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
        "Sales Invoice": {
            "before_save": "kenya_etims_compliance.custom_methods.sales_invoice.validate",
            "before_submit": "kenya_etims_compliance.custom_methods.sales_invoice.trnsSalesSaveWrReq",
            "on_update": "kenya_etims_compliance.custom_methods.sales_invoice.insert_invoice_number"
        },
        "Stock Entry": {
            "before_submit": "kenya_etims_compliance.custom_methods.stock.update_stock_to_etims",
            "before_validate": "kenya_etims_compliance.custom_methods.stock.insert_tax_rate_and_amount",
        },
        "Item": {
            "before_save": "kenya_etims_compliance.custom_methods.item.autofill_tims_info"
        },
        "Purchase Invoice": {
            "before_save": "kenya_etims_compliance.custom_methods.purchase_invoice.validate",
            "before_submit": "kenya_etims_compliance.custom_methods.purchase_invoice.trnsPurchaseSaveReq",
            "on_update": "kenya_etims_compliance.custom_methods.purchase_invoice.insert_invoice_number",
            "on_change": "kenya_etims_compliance.custom_methods.purchase_invoice.add_taxes",
        }
        # "eTIMS Purchase Invoice": {
        #     "on_update": "kenya_etims_compliance.custom_methods.etims_purchase_invoice.update_stock_to_etims",
        # },
        # "eTIMS Stock Movement": {
        #     "on_update": "kenya_etims_compliance.custom_methods.etims_stock_movement.update_stock_to_etims",
        # }
}
# Scheduled Tasks
# ---------------

# scheduler_events = {
#	"all": [
#		"kenya_etims_compliance.tasks.all"
#	],
#	"daily": [
#		"kenya_etims_compliance.tasks.daily"
#	],
#	"hourly": [
#		"kenya_etims_compliance.tasks.hourly"
#	],
#	"weekly": [
#		"kenya_etims_compliance.tasks.weekly"
#	],
#	"monthly": [
#		"kenya_etims_compliance.tasks.monthly"
#	],
# }

# Testing
# -------

# before_tests = "kenya_etims_compliance.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
#	"frappe.desk.doctype.event.event.get_events": "kenya_etims_compliance.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
#	"Task": "kenya_etims_compliance.task.get_dashboard_data"
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
#	{
#		"doctype": "{doctype_1}",
#		"filter_by": "{filter_by}",
#		"redact_fields": ["{field_1}", "{field_2}"],
#		"partial": 1,
#	},
#	{
#		"doctype": "{doctype_2}",
#		"filter_by": "{filter_by}",
#		"partial": 1,
#	},
#	{
#		"doctype": "{doctype_3}",
#		"strict": False,
#	},
#	{
#		"doctype": "{doctype_4}"
#	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
#	"kenya_etims_compliance.auth.validate"
# ]

fixtures = ["Custom Field"]
