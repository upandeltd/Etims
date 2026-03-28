# Copyright (c) 2024, Upande Ltd and contributors
# For license information, please see license.txt

import traceback

import frappe
from frappe.model.document import Document
from kenya_etims_compliance.utils.etims_utils import eTIMS
from kenya_etims_compliance.utils.kra_client import KRAClient


class eTIMSInsurance(Document):
    @frappe.whitelist()
    def bhfInsuranceSaveReq(self):
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
                result = KRAClient().post("saveBhfInsurance", payload)

                if result.get("Error"):
                    return {"Error": result.get("Error")}

                insurance_item.saved = 1
                self.save()
                return {"Success": "Insurance saved"}

            except Exception as e:
                frappe.log_error(title="Insurance", message=traceback.format_exc())
                return {"Error":"Oops Bad Request!"}
