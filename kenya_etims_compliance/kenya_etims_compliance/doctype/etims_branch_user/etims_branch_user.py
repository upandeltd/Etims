# Copyright (c) 2024, Upande Ltd and contributors
# For license information, please see license.txt

import traceback

import frappe
from frappe.model.document import Document
from kenya_etims_compliance.utils.etims_utils import eTIMS
from kenya_etims_compliance.utils.kra_client import KRAClient


class eTIMSBranchUser(Document):
    @frappe.whitelist()
    def bhfUserSaveReq(self):
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
                "regrId":user.get("registration_id"),
                "regrNm":user.get("registration_name"),
                "modrId":user.get("modifier_id"),
                "modrNm":user.get("modifier_name")
            }

            try:
                result = KRAClient().post("saveBhfUser", payload)

                if result.get("Error"):
                    return {"Error": result.get("Error")}

                user.saved = 1
                user.save()
                return {"Success": "Branch user saved"}

            except Exception as e:
                frappe.log_error(title="User Register", message=traceback.format_exc())
                return {"Error":"Oops Bad Request!"}
