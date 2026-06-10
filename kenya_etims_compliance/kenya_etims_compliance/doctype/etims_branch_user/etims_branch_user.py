# Copyright (c) 2024, Upande Ltd and contributors
# For license information, please see license.txt

import requests, traceback

import frappe
from frappe import _
from frappe.model.document import Document
from kenya_etims_compliance.utils.etims_utils import eTIMS


# KRA caps these identifier fields at 20 characters (saveBhfUser spec).
KRA_ID_MAX_LEN = 20


class eTIMSBranchUser(Document):
    def validate(self):
        """Guard KRA field limits and keep the Frappe-login link in sync.

        KRA rejects a ``userId`` longer than 20 chars (e.g. most email addresses),
        so catch it here with a clear message instead of KRA's cryptic
        "length must be between 0 and 20". The ``user_id`` is the KRA identifier;
        the Frappe login is held in ``system_user`` (used to match an item's
        creator/modifier), so auto-link it when ``user_id`` is itself a login.
        """
        if self.user_id and len(self.user_id) > KRA_ID_MAX_LEN:
            frappe.throw(
                _(
                    "User ID '{0}' is {1} characters. KRA limits the user ID to {2}. "
                    "Use a short identifier here (e.g. a username) and set 'System User' "
                    "to the full Frappe login."
                ).format(self.user_id, len(self.user_id), KRA_ID_MAX_LEN)
            )
        if not self.system_user and self.user_id and frappe.db.exists("User", self.user_id):
            self.system_user = self.user_id
        if not self.system_user:
            frappe.msgprint(
                _(
                    "Set 'System User' to the Frappe login of this branch user — it is "
                    "required so eTIMS can recognise the creator/modifier when registering items."
                ),
                indicator="orange",
                title=_("System User not set"),
            )

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
                "regrId":(user.get("registration_name") or "")[:KRA_ID_MAX_LEN],
                "regrNm":user.get("registration_name"),
                "modrId":(user.get("modifier_name") or "")[:KRA_ID_MAX_LEN],
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

            except Exception as e:
                frappe.log_error(frappe.get_traceback(), "User Register")
                raise e