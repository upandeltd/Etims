import traceback
from datetime import datetime

import frappe

from kenya_etims_compliance.utils.etims_utils import eTIMS


@frappe.whitelist()
def get_org_user_info():
	"""Get organization and user information from KRA eTIMS"""
	frappe.has_permission("eTIMS Settings", "read", throw=True)
	response = eTIMS.selectOrgUsrInfo()

	for key, value in response.items():
		if key == "Success":
			return {"Success": value}
		else:
			eTIMS.log_errors("Organization User Info", value)
			return {"Error": value}
