import frappe


def after_install():
	"""Run after app installation to create required single DocType records."""
	create_etims_settings()


def create_etims_settings():
	"""Create eTIMS Settings single record if it doesn't exist."""
	if not frappe.db.exists("eTIMS Settings"):
		frappe.get_doc({"doctype": "eTIMS Settings"}).insert(ignore_permissions=True)
		frappe.db.commit()


def setup_workspace_sidebar():
	"""Conditionally set up Workspace Sidebar fixtures (v16+ only).

	import_file_by_path does not exist in v15.
	Version-guarded with try/except ImportError.
	"""
	if not frappe.db.exists("DocType", "Workspace Sidebar"):
		return

	from kenya_etims_compliance.utils.version_utils import is_v16_or_later

	if not is_v16_or_later():
		return

	if not frappe.db.exists("Workspace Sidebar", {"module": "Kenya Etims Compliance"}):
		try:
			import os

			from frappe.modules.import_file import import_file_by_path

			sidebar_path = os.path.join(
				os.path.dirname(__file__),
				"..",
				"kenya_etims_compliance",
				"workspace_sidebar",
				"etims_compliance.json",
			)
			if os.path.exists(sidebar_path):
				import_file_by_path(sidebar_path)
		except ImportError:
			pass  # import_file_by_path not available on this Frappe version
		except Exception as e:
			frappe.log_error(title="eTIMS: Workspace sidebar import failed", message=str(e))
			pass  # Not critical - workspace JSON handles navigation
