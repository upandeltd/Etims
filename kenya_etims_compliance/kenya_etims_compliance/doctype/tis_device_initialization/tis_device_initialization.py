# Copyright (c) 2024, Upande Ltd and contributors
# For license information, please see license.txt
import requests, traceback

import frappe
from frappe.model.document import Document
from kenya_tims_compliance.utils.etims_utils import eTIMS

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
            response = requests.request(
                        "POST",
                        eTIMS.tims_base_url() + 'selectInitOsdcInfo',
                        json = payload
                    )
            response_data = response.json()
            response_json = eTIMS.get_response_data(response_data)
            
            
            if not response_json.get("resultCd") == '000':
            
                return {"Error":response_json.get("resultMsg")}
         
            data = response_json.get("data")
            if data:
                info = data.get("info")
                self.communication_key = info.get("cmcKey")
                self.device_id = info.get("dvcId")
                self.sales_control_unit_id = info.get("sdcId")
                self.mrc_no = info.get("mrcNo")
                save_communication_key(info.get("cmcKey"), self.branch_id)
                

            self.save()
            return {"Success":response_json.get("resultMsg")}

        except:
            eTIMS.log_errors("TIS Device Verification", traceback.format_exc())
            return {"Error":"Oops Bad Request!"}
        
        
def save_communication_key(comKey, branch_id):
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
    