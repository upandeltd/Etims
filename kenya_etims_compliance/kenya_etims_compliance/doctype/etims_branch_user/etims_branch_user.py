# Copyright (c) 2024, Upande Ltd and contributors
# For license information, please see license.txt

import requests, traceback

import frappe
from frappe.model.document import Document
from kenya_etims_compliance.utils.etims_utils import eTIMS


class eTIMSBranchUser(Document):
    @frappe.whitelist()
    def bhfUserSaveReq(self):
        headers = eTIMS.get_headers()
        user = self
        if not user.get("saved") == 1:
            payload = {
                "userId":user.get("user_id"),
                "userNm":user.get("user_name"),
                "pwd":user.get("password"),
                "adrs":user.get("address"),
                "cntc":user.get("contact"),
                "authCd":user.get("authority_code"),
                "remark":user.get("remark"),
                "useYn":user.get("used_unused"),
                "regrId":user.get("registration_name"), 
                "regrNm":user.get("registration_name"), 
                "modrId":user.get("modifier_name"),
                "modrNm":user.get("modifier_name")
            }
    
            try:
                response = requests.request(
                    "POST", 
                    eTIMS.tims_base_url() + 'saveBhfUser', 
                    json=payload, 
                    headers=headers
                )
                response_json = response.json()

                if not response_json.get("resultCd") == '000':
                    return {"Error":response_json.get("resultMsg")}

                user.saved = 1
                user.save()
                return {"Success":response_json.get("resultMsg")}

            except:
                eTIMS.log_errors("User Register", traceback.format_exc())
                return {"Error":"Oops Bad Request!"}	