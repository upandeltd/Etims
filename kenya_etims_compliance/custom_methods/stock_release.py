import traceback
from datetime import datetime

import frappe
from frappe import _
from frappe.utils import cint

from kenya_etims_compliance.utils.etims_utils import eTIMS
from kenya_etims_compliance.utils.permissions import can_sync_to_etims, require


@frappe.whitelist()
def sync_stock_release_number(sar_no, org_sar_no=0, sar_type=None):
	"""Sync stock release number with KRA eTIMS

	Args:
	    sar_no: Stock release number
	    org_sar_no: Original stock release number (default: 0)
	    sar_type: SAR type code (optional, will use settings default if not provided)
	"""
	if not can_sync_to_etims("eTIMS Stock Release Number"):
		frappe.throw(
			_("Permission Denied: you do not have permission to sync to eTIMS."),
			frappe.PermissionError,
		)

	# Validate numeric inputs
	sar_no = cint(sar_no)
	if sar_no <= 0:
		frappe.throw(_("Invalid stock release number."), frappe.ValidationError)

	# org_sar_no defaults to 0 ("no original SAR"), so allow 0 but reject negatives
	org_sar_no = cint(org_sar_no)
	if org_sar_no < 0:
		frappe.throw(_("Invalid original stock release number."), frappe.ValidationError)

	# Validate sar_type: must be a short non-empty string when provided
	if sar_type is not None:
		sar_type = str(sar_type).strip()
		if not sar_type or len(sar_type) > 10:
			frappe.throw(_("Invalid SAR type."), frappe.ValidationError)

	# Use settings to get default SAR type if not provided
	if sar_type is None:
		from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import (
			get_etims_settings,
		)

		settings = get_etims_settings()
		sar_type = settings.get("default_sar_type_sales", "11")

	response = eTIMS.stockReleaseNoSaveReq(sar_no, org_sar_no, sar_type)

	for key, value in response.items():
		if key == "Success":
			return {"Success": value}
		else:
			eTIMS.log_errors("Stock Release Number Sync", value)
			return {"Error": value}


@frappe.whitelist()
def search_stock_release_no(sar_no=None, last_req_dt=None):
	"""Search stock release numbers"""
	# Proxies a KRA lookup on the company's credentials, so it must not be
	# reachable by any authenticated session.
	require("eTIMS Stock Release Number", "read")

	response = eTIMS.searchStockReleaseNo(sar_no, last_req_dt)

	for key, value in response.items():
		if key == "Success":
			return {"Success": value}
		else:
			eTIMS.log_errors("Stock Release Number Search", value)
			return {"Error": value}


@frappe.whitelist()
def get_stock_release_list(last_req_dt=None):
	"""Get stock release number list"""
	# Proxies a KRA lookup on the company's credentials, so it must not be
	# reachable by any authenticated session.
	require("eTIMS Stock Release Number", "read")

	response = eTIMS.selectStockReleaseNoList(last_req_dt)

	for key, value in response.items():
		if key == "Success":
			return {"Success": value}
		else:
			eTIMS.log_errors("Stock Release Number List", value)
			return {"Error": value}
