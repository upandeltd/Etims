__version__ = "0.0.1"


def check_app_permission():
	import frappe

	if frappe.session.user == "Administrator":
		return True
	user_type = frappe.get_cached_value("User", frappe.session.user, "user_type")
	if user_type == "Website User":
		return False
	return True
