import traceback
from datetime import datetime

import frappe
from kenya_etims_compliance.utils.etims_utils import eTIMS


@frappe.whitelist()
def sync_stock_release_number(sar_no, org_sar_no=0, sar_type=None):
    """Sync stock release number with KRA eTIMS

    Args:
        sar_no: Stock release number
        org_sar_no: Original stock release number (default: 0)
        sar_type: SAR type code (optional, will use settings default if not provided)
    """
    # Use settings to get default SAR type if not provided
    if sar_type is None:
        from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import get_etims_settings
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
    response = eTIMS.selectStockReleaseNoList(last_req_dt)

    for key, value in response.items():
        if key == "Success":
            return {"Success": value}
        else:
            eTIMS.log_errors("Stock Release Number List", value)
            return {"Error": value}
