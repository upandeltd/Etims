# Copyright (c) 2024, Upande Ltd and contributors
# For license information, please see license.txt

import requests, traceback

import frappe
from frappe import _
from frappe.model.document import Document
from kenya_etims_compliance.utils.etims_utils import eTIMS


# KRA caps these identifier fields at 20 characters (saveBhfUser spec).
KRA_ID_MAX_LEN = 20

# saveBhfUser payload keys KRA limits to 20 chars (identifiers/codes — NOT the
# free-text name/address/remark fields, which allow more). Used to name the
# offending field instead of KRA's blank "[ : length must be between 0 and 20]".
KRA_BHF_USER_SHORT_FIELDS = ("userId", "pwd", "cntc", "authCd", "useYn", "regrId", "modrId")


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
    
            # Pre-flight: name any 20-char-capped field that is too long, so the
            # user gets an actionable error instead of KRA's blank-field one.
            too_long = {
                k: len(payload[k])
                for k in KRA_BHF_USER_SHORT_FIELDS
                if isinstance(payload.get(k), str) and len(payload[k]) > KRA_ID_MAX_LEN
            }
            if too_long:
                frappe.throw(
                    _("These fields exceed KRA's {0}-character limit: {1}. Shorten them and retry.").format(
                        KRA_ID_MAX_LEN,
                        ", ".join("{0} ({1} chars)".format(k, v) for k, v in too_long.items()),
                    ),
                    title=_("Field too long for KRA"),
                )

            try:
                response = requests.request(
                    "POST",
                    eTIMS.tims_base_url() + 'saveBhfUser',
                    json=payload,
                    headers=headers
                )
                response_json = response.json()

                if not response_json.get("resultCd") == '000':
                    # KRA hides the offending field; log every field length so it
                    # can be identified from the Error Log.
                    field_lengths = {
                        k: (len(v) if isinstance(v, str) else v) for k, v in payload.items()
                    }
                    frappe.log_error(
                        message="saveBhfUser rejected: {0}\nField lengths: {1}".format(
                            response_json.get("resultMsg"), field_lengths
                        ),
                        title="eTIMS Branch User register failed",
                    )
                    return {"Error":response_json.get("resultMsg")}

                user.saved = 1
                user.save()
                return {"Success":response_json.get("resultMsg")}

            except Exception as e:
                frappe.log_error(frappe.get_traceback(), "User Register")
                raise e