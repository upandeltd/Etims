# Copyright (c) 2024, Upande Ltd and contributors
# For license information, please see license.txt
import traceback

import frappe
from frappe.model.document import Document
from kenya_etims_compliance.utils.etims_utils import eTIMS
from kenya_etims_compliance.kenya_etims_compliance.doctype.etims_settings.etims_settings import get_api_url
from kenya_etims_compliance.utils.kra_client import KRAClient


class TISDeviceInitialization(Document):
	# Method to initialize and verify a device with etims
    @frappe.whitelist()
    def deviceVerificationReq(self):
        payload = {
            "tin": self.pin,
            "bhfId": self.branch_id,
            "dvcSrlNo" : self.device_serial_number
        }

        try:
            # For device initialization, we create a KRAClient that will have
            # empty headers since no active TIS Device exists yet.
            # We override the base URL manually via the post endpoint.
            api_url = get_api_url(self.api_mode or "Sandbox")

            # Use KRAClient with empty headers for bootstrap endpoint
            client = KRAClient()
            # Override headers to empty since selectInitOsdcInfo doesn't need auth
            client.headers = {}
            # Store original _get_base_url and override
            original_get_base_url = client._get_base_url
            client._get_base_url = lambda: api_url

            result = client.post("selectInitOsdcInfo", payload)

            if result.get("Error"):
                return {"Error": result.get("Error")}

            data = result.get("Success")
            if data:
                info = data.get("info")
                self.communication_key = info.get("cmcKey")
                self.device_id = info.get("dvcId")
                self.sales_control_unit_id = info.get("sdcId")
                self.mrc_no = info.get("mrcNo")
                save_communication_key(info.get("cmcKey"), self.branch_id)

            self.save()
            return {"Success": "Device verification completed"}

        except Exception as e:
            error_msg = traceback.format_exc()
            frappe.log_error(title="TIS Device Verification", message=error_msg)
            return {"Error": f"Device initialization failed. Check Error Log for details."}

    @frappe.whitelist()
    def refresh_org_info(self):
        """Refresh organization info from KRA"""
        from kenya_etims_compliance.custom_methods.organization import get_org_user_info

        result = get_org_user_info()

        if result.get("Error"):
            frappe.throw(result.get("Error"))

        return result

#Method to create communication key and stores it in communication key doctype
def save_communication_key(comKey, branch_id):
    """_summary_

    Args:
        comKey (_str_): _TIS communication key_
        branch_id (_str_): _branch id_
    """
    doc_exits = frappe.db.exists("TIS Communication Key", {"branch_id": branch_id})

    if not doc_exits:
        new_doc = frappe.new_doc("TIS Communication Key")
        new_doc.branch_id = branch_id
        new_doc.communication_key = comKey

        new_doc.insert()
    else:
        new_doc = frappe.get_doc("TIS Communication Key", doc_exits)
        new_doc.communication_key = comKey

        new_doc.save()
