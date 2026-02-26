import frappe


def after_install():
	"""Run after app installation to create required single DocType records."""
	create_etims_settings()


def create_etims_settings():
	"""Create eTIMS Settings single record if it doesn't exist."""
	if not frappe.db.exists("eTIMS Settings"):
		frappe.get_doc({"doctype": "eTIMS Settings"}).insert(ignore_permissions=True)
		frappe.db.commit()
