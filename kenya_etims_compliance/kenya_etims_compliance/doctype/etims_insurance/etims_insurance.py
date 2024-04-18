# Copyright (c) 2024, Upande Ltd and contributors
# For license information, please see license.txt

import requests, traceback

import frappe
from frappe.model.document import Document
from kenya_etims_compliance.utils.etims_utils import eTIMS


class eTIMSInsurance(Document):
    @frappe.whitelist()
    def bhfInsuranceSaveReq(self):
        headers = eTIMS.get_headers()
        insurance_item = self
        if not insurance_item.get("saved") == 1:
            payload = {
                "isrccCd": insurance_item.get("insurance_code"),
                "isrccNm": insurance_item.get("insurance_name"),
                "isrcRt": insurance_item.get("premium_rate"),
                "useYn": insurance_item.get("usedunused"),
                "regrId": insurance_item.get("registration_id"),
                "regrNm": insurance_item.get("registration_name"),
                "modrId": insurance_item.get("modifier_id"),
                "modrNm": insurance_item.get("modifier_name")
            }

            try:
                response = requests.request(
                    "POST", 
                    eTIMS.tims_base_url() + 'saveBhfInsurance', 
                    json = payload, 
                    headers=headers
                )
                response_json = response.json()
    
                if not response_json.get("resultCd") == '000':
                    return {"Error":response_json.get("resultMsg")}
        
                insurance_item.saved = 1
                self.save()
                return {"Success":response_json.get("resultMsg")}

            except:
                eTIMS.log_errors("Insurance", traceback.format_exc())
                return {"Error":"Oops Bad Request!"}